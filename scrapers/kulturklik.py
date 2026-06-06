"""
kulturklik.py
Kulturklik ekitaldiak Open Data Euskadi JSON deskargatik lortu.

JSON eremu izenak (egiaztatuak):
  documentName        → ekitaldiaren izena
  documentDescription → azalpena
  eventType           → mota
  eventStartDate      → hasiera data
  eventEndDate        → bukaera data
  eventTownName       → herria
  eventLocationName   → antzokiaren izena
  eventLocation       → helbidea (alternatibo)
  eventWhere          → lekuaren deskribapena (alternatibo)
  eventPrice          → prezioa
  eventTimeTable      → ordutegiaen deskribapena
  eventLanguages      → hizkuntza
  eventImageUrl       → irudiaren URL
  eventSourceUrl      → jatorrizko URLa
  friendlyUrl         → URLa (alternatibo)
  physicalUrl         → URLa (alternatibo)
  eventStatus         → egoera (cancelado/suspendido detektatzeko)
  territory           → lurraldea/herrialdea
  latwgs84            → latitudea
  lonwgs84            → longitudea
"""

import re
import yaml
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

CONFIG_PATH = Path(__file__).parent.parent / "config" / "iturriak.yml"


class KulturklikScraper(BaseScraper):
    BASE_HTML = "https://www.kulturklik.euskadi.eus"

    def __init__(self):
        cfg = yaml.safe_load(CONFIG_PATH.read_text())["iturriak"]["kulturklik"]
        super().__init__("kulturklik", eskaera_tartea=cfg["eskaera_tartea"])
        self.json_url = cfg["json_url"]
        self.egun_url = cfg["egun_url"]
        self.baztertu_kategoriak = {
            k.lower() for k in cfg.get("baztertu_kategoriak", [])
        }

    # ------------------------------------------------------------------

    def lortu_ekitaldiak(self) -> list[dict]:
        self.logger.info("Kulturklik: JSON deskarga saiatzen...")
        ekitaldiak = self._json_bidez()
        if ekitaldiak:
            return ekitaldiak
        self.logger.warning("JSON huts — HTML scraping-era jaisten...")
        return self._html_bidez()

    # ------------------------------------------------------------------
    # JSON deskarga
    # ------------------------------------------------------------------

    def _json_bidez(self) -> list[dict]:
        erantzuna = self.eskatu(self.json_url, curl_lehentasuna=True)
        if not erantzuna:
            return []
        try:
            datuak = erantzuna.json()
        except Exception as e:
            self.logger.error("JSON parseaketa huts: %s", e)
            return []

        if isinstance(datuak, dict):
            datuak = datuak.get("events", datuak.get("eventos", datuak.get("results", [])))
        if not isinstance(datuak, list) or not datuak:
            self.logger.error("JSON formatua ezezaguna edo hutsa")
            return []

        gaur = datetime.today().date()
        ekitaldiak = []
        baztertuta = {"erakusketa": 0, "iragana": 0, "bertan_behera": 0}

        for sarrera in datuak:
            # Erakusketak baztertu
            mota_raw = (sarrera.get("eventType") or "").strip()
            if mota_raw.lower() in self.baztertu_kategoriak:
                baztertuta["erakusketa"] += 1
                continue

            # Bertan behera / suspendituak baztertu (eventStatus eremua)
            status = (sarrera.get("eventStatus") or "").lower()
            if any(h in status for h in ["cancel", "suspend", "anula"]):
                baztertuta["bertan_behera"] += 1
                continue

            # Iraganeko ekitaldiak baztertu
            data_str = sarrera.get("eventStartDate") or sarrera.get("eventSearchDate1") or ""
            if data_str:
                try:
                    data = datetime.fromisoformat(str(data_str)[:10]).date()
                    if data < gaur:
                        baztertuta["iragana"] += 1
                        continue
                except (ValueError, TypeError):
                    pass

            ekitaldia = self._bihurtu_sarrera(sarrera)
            if ekitaldia:
                ekitaldiak.append(ekitaldia)

        self.logger.info(
            "Kulturklik JSON: %d ekitaldi (baztertuta: %d erakusketa, %d iraganeko, %d bertan behera)",
            len(ekitaldiak), baztertuta["erakusketa"], baztertuta["iragana"], baztertuta["bertan_behera"]
        )
        return ekitaldiak

    # Telebistako kanalak — non eremuan agertzen badira, baztertu
    TELEBISTA_KANALAK = {"primeran", "makusi", "prime video"}

    # Zine aretoak — non eremuan agertzen badira, baztertu
    ZINE_ARETOAK = re.compile(r"\bcine\b", re.IGNORECASE)

    # Bisita-ekitaldiak — izenburuan agertzen badira, baztertu
    BISITA_HITZAK = re.compile(r"\bvisita[s]?\b", re.IGNORECASE)

    # Herri anitzen adierazleak — baztertu
    HERRI_ANITZ = re.compile(r",", re.IGNORECASE)

    def _bihurtu_sarrera(self, s: dict) -> dict | None:
        # Izenburua — _eu eremua lehenik (euskarazkoa), gero generikoa
        izena = self.garbitu_izenburua(
            s.get("documentName_eu") or s.get("documentName") or ""
        )
        if not izena:
            return None

        # Bisita-ekitaldiak baztertu
        if self.BISITA_HITZAK.search(izena):
            return None

        # Datak eta ordua bereizita
        hasiera_data, hasiera_ordua = self._data_eta_ordua(
            s.get("eventStartDate") or s.get("eventSearchDate1") or "",
            s.get("eventTimeTable") or ""
        )

        # [6] Hasiera ordua ezezaguna → baztertu
        if not hasiera_ordua:
            return None

        # Lekua — _eu eremuak lehenik
        antzoki = self.garbitu_testua(
            s.get("eventLocationName_eu") or s.get("eventLocationName")
            or s.get("eventLocation") or s.get("eventWhere")
            or s.get("placename") or ""
        )

        # Telebistako kanalak baztertu
        if antzoki.strip().lower() in self.TELEBISTA_KANALAK:
            return None

        # Zine aretoak baztertu
        if self.ZINE_ARETOAK.search(antzoki):
            return None

        # non eremua hutsik → baztertu
        if not antzoki.strip():
            return None

        # Herria — _eu eremua lehenik
        herria = self.garbitu_testua(
            s.get("eventTownName_eu") or s.get("eventTownName")
            or s.get("municipality") or ""
        )

        # Herri anitz → baztertu
        if herria and "," in herria:
            return None

        # Herrialdea — _eu eremua lehenik
        herrialdea = self.garbitu_testua(
            s.get("eventTerritoryName_eu") or s.get("eventTerritoryName")
            or s.get("territory") or ""
        )

        # Koordenatuak
        koordenatuak = []
        try:
            lat = s.get("latwgs84")
            lon = s.get("lonwgs84")
            if lat and lon:
                koordenatuak = [float(lat), float(lon)]
        except (ValueError, TypeError):
            pass

        lekua = {
            "non": antzoki,
            "herria": herria,
            "herrialdea": herrialdea,
            "koordenatuak": koordenatuak,
        }

        # Prezioa — [8] moneta eta doan kendu
        prezio_raw = self.garbitu_prezioa(str(s.get("eventPrice") or ""))
        prezioa = prezio_raw.get("zenbatekoa")

        # Azalpena — _eu eremua lehenik
        azalpena = self.garbitu_testua(
            s.get("documentDescription_eu") or s.get("documentDescription") or ""
        )
        azalpena = re.sub(r"<[^>]+>", "", azalpena)[:800]

        # URL
        url = (
            s.get("eventSourceUrl")
            or s.get("friendlyUrl")
            or s.get("physicalUrl")
            or ""
        )

        # Irudia
        irudi_url = s.get("eventImageUrl") or ""

        # Hizkuntza
        hizkuntza = self._normalizatu_hizkuntza(s.get("eventLanguages") or "")

        # Mota — _eu eremua lehenik
        mota = self.garbitu_testua(
            s.get("eventType_eu") or s.get("eventType") or ""
        )

        return {
            "ekitaldia": izena,
            "azalpena": azalpena,
            "mota": mota,
            "hizkuntza": hizkuntza,
            "hasiera_data": hasiera_data,
            "hasiera_ordua": hasiera_ordua,
            "lekua": lekua,
            "prezioa": prezioa,
            "url": url,
            "irudiaren_url": irudi_url,
            "iturria": "kulturklik.eus",
            "etiketak": [],
            "nabarmendua": "0",
        }

    # ------------------------------------------------------------------
    # HTML scraping (fallback)
    # ------------------------------------------------------------------

    def _html_bidez(self) -> list[dict]:
        ekitaldiak = []
        ikusi_urlak = set()
        gaur = datetime.today()

        for i in range(30):
            egun = gaur + timedelta(days=i)
            data_str = egun.strftime("%d/%m/%Y")
            url = self.egun_url.format(data=data_str)
            erantzuna = self.eskatu(url)
            if not erantzuna:
                continue

            soup = BeautifulSoup(erantzuna.text, "lxml")
            for karta in soup.select("li"):
                mota_el = karta.select_one(".event-type, span.type")
                if mota_el and mota_el.get_text().strip().lower() in self.baztertu_kategoriak:
                    continue
                lotura = karta.select_one("h4 a, h3 a")
                if not lotura:
                    continue
                ekitaldi_url = lotura.get("href", "")
                if not ekitaldi_url or ekitaldi_url in ikusi_urlak:
                    continue
                if not ekitaldi_url.startswith("http"):
                    ekitaldi_url = self.BASE_HTML + ekitaldi_url
                ikusi_urlak.add(ekitaldi_url)
                ekitaldia = self._xehetasunak_html(ekitaldi_url, egun)
                if ekitaldia:
                    ekitaldiak.append(ekitaldia)

        self.logger.info("Kulturklik HTML: %d ekitaldi", len(ekitaldiak))
        return ekitaldiak

    def _xehetasunak_html(self, url: str, egun: datetime) -> dict | None:
        erantzuna = self.eskatu(url)
        if not erantzuna:
            return None
        soup = BeautifulSoup(erantzuna.text, "lxml")
        h2 = soup.select_one("h2")
        izena = self.garbitu_izenburua(h2.get_text() if h2 else "")
        if not izena:
            return None
        mota_el = soup.select_one(".event-type")
        mota = self.garbitu_testua(mota_el.get_text() if mota_el else "")
        if mota.lower() in self.baztertu_kategoriak:
            return None
        hasiera_data = egun.strftime("%Y-%m-%d")
        ordu_el = soup.find(string=re.compile(r"Ordutegia|Horario", re.I))
        if ordu_el and ordu_el.parent:
            ordu_ondoan = ordu_el.parent.find_next_sibling()
            if ordu_ondoan:
                m = re.search(r"(\d{1,2}):(\d{2})", ordu_ondoan.get_text())
                if m:
                    hasiera_data = egun.replace(
                        hour=int(m.group(1)), minute=int(m.group(2)),
                        second=0, microsecond=0
                    ).isoformat()
        leku_el = soup.find(string=re.compile(r"^Lekua$|^Lugar$", re.I))
        antzoki, herria = "", ""
        if leku_el and leku_el.parent:
            leku_ondoan = leku_el.parent.find_next_sibling()
            if leku_ondoan:
                lerroak = [l.strip() for l in leku_ondoan.get_text("\n").split("\n") if l.strip()]
                if lerroak:
                    antzoki = self.garbitu_testua(lerroak[0])
                for l in lerroak[1:]:
                    if re.search(r"[A-ZÁÉÍÓÚ]", l):
                        herria = self.garbitu_testua(l)
                        break
        prezio_el = soup.find(string=re.compile(r"Zenbatekoa|Precio", re.I))
        prezio_str = ""
        if prezio_el and prezio_el.parent:
            p = prezio_el.parent.find_next_sibling()
            if p:
                prezio_str = p.get_text()
        azalpen_el = soup.select_one("article p")
        azalpena = self.garbitu_testua(azalpen_el.get_text() if azalpen_el else "")[:800]
        irudi_el = soup.select_one("article img")
        irudi_url = irudi_el.get("src", "") if irudi_el else ""
        if irudi_url and not irudi_url.startswith("http"):
            irudi_url = self.BASE_HTML + irudi_url
        return {
            "ekitaldia": izena,
            "azalpena": azalpena,
            "mota": mota,
            "hizkuntza": "",
            "hasiera_data": hasiera_data,
            "bukaera_data": "",
            "lekua": {"non": antzoki, "herria": herria, "herrialdea": "", "koordenatuak": []},
            "prezioa": self.garbitu_prezioa(prezio_str),
            "url": url,
            "irudiaren_url": irudi_url,
            "iturria": "kulturklik.eus",
            "etiketak": [],
            "nabarmendua": "0",
        }

    # ------------------------------------------------------------------
    # Laguntzaileak
    # ------------------------------------------------------------------

    @staticmethod
    def _data_eta_ordua(data_str: str, ordutegia_str: str = "") -> tuple[str, str]:
        """
        Data eta ordua bereizita itzuli: (hasiera_data, hasiera_ordua)
        hasiera_data: "YYYY-MM-DD"
        hasiera_ordua: "HH:MM" edo "" ordua ez badago
        """
        data_str = str(data_str).strip() if data_str else ""
        ordua = ""
        data = ""

        if not data_str:
            return "", ""

        # ISO formatua: 2026-07-15T19:30:00
        try:
            dt = datetime.fromisoformat(data_str)
            data = dt.strftime("%Y-%m-%d")
            if dt.hour or dt.minute:
                ordua = dt.strftime("%H:%M")
        except ValueError:
            # dd/mm/yyyy
            m = re.match(r"(\d{2})/(\d{2})/(\d{4})", data_str)
            if m:
                data = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
            else:
                m = re.match(r"(\d{2})-(\d{2})-(\d{4})", data_str)
                if m:
                    data = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                else:
                    data = data_str[:10]

        # Ordua eventTimeTable eremutik atera (oraindik ez badugu)
        if not ordua and ordutegia_str:
            m = re.search(r"(\d{1,2})[:\.](\d{2})", ordutegia_str)
            if m:
                ordua = f"{int(m.group(1)):02d}:{m.group(2)}"

        return data, ordua

    @staticmethod
    def _normalizatu_hizkuntza(hizkuntza_raw: str) -> str:
        """eventLanguages eremua → 'eu' | 'es' | 'fr' | ''"""
        h = hizkuntza_raw.strip().lower()
        if not h:
            return ""
        # Eremu honek hizkuntza-zerrenda izan dezake: "Euskera, Castellano"
        zatiak = re.split(r"[,;/\s]+", h)
        du_eu = any(z in {"eu", "eus", "euskera", "euskara", "basque", "vasco"} for z in zatiak)
        du_es = any(z in {"es", "spa", "castellano", "español", "spanish"} for z in zatiak)
        du_fr = any(z in {"fr", "fra", "français", "frances", "french"} for z in zatiak)
        if du_eu:
            return "eu"
        if du_es:
            return "es"
        if du_fr:
            return "fr"
        return h[:5]  # Ezezaguna: lehen 5 karaktere gorde

    @staticmethod
    def _normalizatu_data(data_str: str) -> str:
        if not data_str:
            return ""
        data_str = str(data_str).strip()
        try:
            return datetime.fromisoformat(data_str).isoformat()
        except ValueError:
            pass
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", data_str)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        # dd-mm-yyyy
        m = re.match(r"(\d{2})-(\d{2})-(\d{4})", data_str)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return data_str
