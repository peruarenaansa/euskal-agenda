"""
musikazuzenean.py
musikazuzenean.eus agendako kontzertuen datuak lortu.

WordPress gunea da, 'ekitaldia' custom post type-arekin.
Bi metodo saiatzen dira:
  1. WordPress REST API (/wp-json/wp/v2/ekitaldia)
  2. HTML scraping hasierako orritik (fallback)

Datuak:
  - Izenburua (taldea/k)
  - Data eta ordua
  - Herria eta herrialdea (dagoeneko euskaraz: BILBO (BIZKAIA))
  - Lekua (antzokia/taberna)
  - Azalpena
  - Sarrera prezioa (batzuetan)
"""

import re
from datetime import datetime, date
from pathlib import Path

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

BASE_URL = "https://musikazuzenean.eus"

# Hilabete izenak (agertzen diren formatuan)
HILABETEAK = {
    "Urt": 1, "Ots": 2, "Mar": 3, "Api": 4, "Mai": 5, "Eka": 6,
    "Uzt": 7, "Abu": 8, "Ira": 9, "Urr": 10, "Aza": 11, "Abe": 12,
    "Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12,
    "Jan": 1, "Feb": 2, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Bertan behera adierazleak
BERTAN_BEHERA = re.compile(r"bertan\s+behera", re.IGNORECASE)


class MusikazuzeneanScraper(BaseScraper):
    def __init__(self):
        super().__init__("musikazuzenean", eskaera_tartea=1.5)

    def lortu_ekitaldiak(self) -> list[dict]:
        # 1. WordPress REST API saiatu
        ekitaldiak = self._api_bidez()
        if ekitaldiak:
            return ekitaldiak

        # 2. HTML scraping (fallback)
        self.logger.warning("API huts — HTML scraping saiatzen...")
        return self._html_bidez()

    # ------------------------------------------------------------------
    # 1. WordPress REST API
    # ------------------------------------------------------------------

    def _api_bidez(self) -> list[dict]:
        gaur = date.today().isoformat()
        # WordPress REST API: ekitaldia custom post type
        # after= parametroak iraganeko ekitaldiak baztertzen ditu
        url = (
            f"{BASE_URL}/wp-json/wp/v2/ekitaldia"
            f"?per_page=100&orderby=date&order=asc"
            f"&after={gaur}T00:00:00"
            f"&_fields=id,title,date,slug,content,excerpt,acf,meta"
        )
        self.logger.info("musikazuzenean API: %s", url)
        erantzuna = self.eskatu(url, curl_lehentasuna=True)
        if not erantzuna:
            return []

        try:
            sarrerak = erantzuna.json()
        except Exception:
            return []

        if not isinstance(sarrerak, list):
            self.logger.warning("API erantzun formatua ezezaguna")
            return []

        ekitaldiak = []
        for s in sarrerak:
            e = self._bihurtu_api_sarrera(s)
            if e:
                ekitaldiak.append(e)

        self.logger.info("musikazuzenean API: %d ekitaldi", len(ekitaldiak))
        return ekitaldiak

    def _bihurtu_api_sarrera(self, s: dict) -> dict | None:
        izena = self.garbitu_izenburua(
            s.get("title", {}).get("rendered") or s.get("title") or ""
        )
        if not izena:
            return None

        # Data WordPress-eko 'date' eremutik
        data_raw = s.get("date") or ""
        hasiera_data, hasiera_ordua = self._data_eta_ordua_wp(data_raw)
        if not hasiera_ordua:
            return None

        # ACF (Advanced Custom Fields) eremuetatik lekua eta herria atera
        acf = s.get("acf") or {}
        herria = self.garbitu_testua(acf.get("herria") or acf.get("udalerria") or "")
        herrialdea = self.garbitu_testua(acf.get("herrialdea") or acf.get("lurraldea") or "")
        antzoki = self.garbitu_testua(acf.get("lekua") or acf.get("aretoa") or "")

        # Azalpena
        azalpena = self.garbitu_testua(
            s.get("excerpt", {}).get("rendered")
            or s.get("content", {}).get("rendered")
            or ""
        )
        azalpena = re.sub(r"<[^>]+>", "", azalpena)[:800]

        url = f"{BASE_URL}/ekitaldia/{s.get('slug', '')}"

        return {
            "ekitaldia": izena,
            "azalpena": azalpena,
            "mota": "musika",
            "hizkuntza": "eu",
            "hasiera_data": hasiera_data,
            "hasiera_ordua": hasiera_ordua,
            "lekua": {
                "non": antzoki,
                "herria": herria,
                "herrialdea": herrialdea,
                "koordenatuak": [],
            },
            "prezioa": None,
            "url": url,
            "irudiaren_url": "",
            "iturria": "musikazuzenean.eus",
            "etiketak": [],
            "nabarmendua": "0",
        }

    # ------------------------------------------------------------------
    # 2. HTML scraping
    # ------------------------------------------------------------------

    def _html_bidez(self) -> list[dict]:
        """
        Hasierako orria scrapeatu.
        Egitura:
          [Larunbata / Igandea / ...]
          [Eguna] [Hilabete]
          [Izena] → link /ekitaldia/slug/
          [HERRIA (HERRIALDEA)]
          [Lekua]
          [BERTAN BEHERA] (aukerakoa)
        """
        erantzuna = self.eskatu(BASE_URL, curl_lehentasuna=True)
        if not erantzuna:
            return []

        soup = BeautifulSoup(erantzuna.text, "lxml")
        ekitaldiak = []
        egun_oraingoa = None
        ordua_oraingoa = ""
        urte_oraingoa = datetime.today().year

        # Orrian blokeak daude: egun-titulua, gero ekitaldiak
        for elementu in soup.select("main *"):
            testua = elementu.get_text(strip=True)

            # Data-blokea: "06 Eka" edo "07 Eka" modukoak
            if elementu.name in ("h2", "h3", "div") and re.match(r"^\d{1,2}\s+[A-Za-z]{3}", testua):
                m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})", testua)
                if m:
                    eguna = int(m.group(1))
                    hilabete_str = m.group(2).capitalize()
                    hilabete = HILABETEAK.get(hilabete_str)
                    if hilabete:
                        # Urtea: hilabetea igaro bada, hurrengo urtea
                        gaur = datetime.today()
                        if hilabete < gaur.month - 1:
                            urte_oraingoa = gaur.year + 1
                        try:
                            egun_oraingoa = date(urte_oraingoa, hilabete, eguna)
                        except ValueError:
                            pass
                continue

            # Ordua: "19:30" modukoak
            if elementu.name == "span" and re.match(r"^\d{1,2}:\d{2}$", testua):
                ordua_oraingoa = testua
                continue

            # Ekitaldi-karta: link /ekitaldia/... duen elementua
            lotura = elementu.select_one("a[href*='/ekitaldia/']")
            if not lotura or not egun_oraingoa:
                continue

            # Ekitaldi-karta berria bakarrik prozesatu (ez azpikartarik)
            if elementu.name not in ("article", "div", "li"):
                continue
            # Ekitaldi-karta osoa behar dugu, ez azpielementu txikiak
            if len(elementu.select("a[href*='/ekitaldia/']")) == 0:
                continue

            # Bertan behera?
            if BERTAN_BEHERA.search(elementu.get_text()):
                continue

            ekitaldi_url = lotura.get("href", "")
            if not ekitaldi_url.startswith("http"):
                ekitaldi_url = BASE_URL + ekitaldi_url

            izena = self.garbitu_izenburua(lotura.get_text(strip=True))
            if not izena:
                continue

            # Herria eta herrialdea: "ANDOAIN (GIPUZKOA)" formatua
            herria, herrialdea = self._parseatu_herria(elementu.get_text())

            # Lekua: herriaren ondoren datorrena
            antzoki = self._parseatu_lekua(elementu.get_text(), herria)

            if not ordua_oraingoa:
                continue  # Ordua ezezaguna → baztertu

            ekitaldiak.append({
                "ekitaldia": izena,
                "azalpena": "",
                "mota": "musika",
                "hizkuntza": "eu",
                "hasiera_data": egun_oraingoa.isoformat(),
                "hasiera_ordua": ordua_oraingoa,
                "lekua": {
                    "non": antzoki,
                    "herria": herria.title(),
                    "herrialdea": herrialdea.title(),
                    "koordenatuak": [],
                },
                "prezioa": None,
                "url": ekitaldi_url,
                "irudiaren_url": "",
                "iturria": "musikazuzenean.eus",
                "etiketak": [],
                "nabarmendua": "0",
            })

        self.logger.info("musikazuzenean HTML: %d ekitaldi", len(ekitaldiak))
        return ekitaldiak

    # ------------------------------------------------------------------
    # Laguntzaileak
    # ------------------------------------------------------------------

    @staticmethod
    def _data_eta_ordua_wp(data_str: str) -> tuple[str, str]:
        """WordPress ISO data → (YYYY-MM-DD, HH:MM)"""
        if not data_str:
            return "", ""
        try:
            dt = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
            ordua = dt.strftime("%H:%M") if (dt.hour or dt.minute) else ""
            return dt.strftime("%Y-%m-%d"), ordua
        except ValueError:
            return data_str[:10], ""

    @staticmethod
    def _parseatu_herria(testua: str) -> tuple[str, str]:
        """
        "ANDOAIN (GIPUZKOA)" → ("ANDOAIN", "GIPUZKOA")
        "BILBO (BIZKAIA)" → ("BILBO", "BIZKAIA")
        """
        m = re.search(r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\-/]+)\s*\(([A-ZÁÉÍÓÚÑ]+)\)", testua)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        # Herrialdea gabe
        m = re.search(r"\b([A-ZÁÉÍÓÚÑ]{3,}(?:\s[A-ZÁÉÍÓÚÑ]+)*)\b", testua)
        if m:
            return m.group(1).strip(), ""
        return "", ""

    @staticmethod
    def _parseatu_lekua(testua: str, herria: str) -> str:
        """Herriaren ondorena atera lekua moduan."""
        if not herria:
            return ""
        # Herriaren ondoren dagoen lerro bakarra
        lerroak = [l.strip() for l in testua.split("\n") if l.strip()]
        herria_lower = herria.lower()
        for i, lerroa in enumerate(lerroak):
            if herria_lower in lerroa.lower():
                if i + 1 < len(lerroak):
                    lekua = lerroak[i + 1].strip()
                    # Kendu diru-prezioak, URL-ak...
                    if not re.match(r"^\d|^http|^www", lekua):
                        return lekua
        return ""
