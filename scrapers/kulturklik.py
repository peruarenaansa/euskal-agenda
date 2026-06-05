"""
kulturklik.py
Kulturklik ekitaldiak Open Data Euskadi JSON deskargatik lortu.

Estrategia:
  1. Lehentasuna: Open Data Euskadi JSON fitxategia deskargatu
     (kulturklik.json — ekitaldi guztiak, dauden guztiak)
  2. Fallback: HTML scraping (egun-egun, aurrerako 30 egunetan)

Erakusketa kategoriak baztertzen dira iturriak.yml-en zerrenda bidez.

JSON fitxategiko eremu garrantzitsuenak (ikertutakoak):
  documentName / nombre  → izenburua
  eventType / tipoEvento → mota
  dateStart / fechaInicio → hasiera data
  dateEnd / fechaFin     → bukaera data
  municipalityName       → herria
  placeName              → lekua
  price / precio         → prezioa
  documentUrl            → URLa
  imageUrl               → irudia
  documentLanguage       → hizkuntza
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
    # 1. METODOA: JSON deskarga (Open Data Euskadi)
    # ------------------------------------------------------------------

    def _json_bidez(self) -> list[dict]:
        erantzuna = self.eskatu(self.json_url)
        if not erantzuna:
            return []
        try:
            datuak = erantzuna.json()
        except Exception as e:
            self.logger.error("JSON parseaketa huts: %s", e)
            return []

        if not isinstance(datuak, list):
            datuak = datuak.get("events", datuak.get("eventos", []))

        gaur = datetime.today().date()
        ekitaldiak = []
        for sarrera in datuak:
            # Iraganeko ekitaldiak baztertu
            data_str = (
                sarrera.get("dateStart")
                or sarrera.get("fechaInicio")
                or sarrera.get("startDate")
                or ""
            )
            if data_str:
                try:
                    data = datetime.fromisoformat(data_str[:10]).date()
                    if data < gaur:
                        continue
                except ValueError:
                    pass

            # Erakusketak baztertu
            mota_raw = (
                sarrera.get("eventType")
                or sarrera.get("tipoEvento")
                or sarrera.get("type")
                or ""
            )
            if mota_raw.lower() in self.baztertu_kategoriak:
                continue

            ekitaldia = self._bihurtu_json_sarrera(sarrera)
            if ekitaldia:
                ekitaldiak.append(ekitaldia)

        self.logger.info("Kulturklik JSON: %d ekitaldi (erakusketak gabe)", len(ekitaldiak))
        return ekitaldiak

    def _bihurtu_json_sarrera(self, s: dict) -> dict | None:
        """Open Data Euskadi JSON sarrera → gure eskema."""
        # Izenburua — eremu posibleak
        izena = (
            s.get("documentName_eu") or s.get("documentName")
            or s.get("nombre_eu") or s.get("nombre")
            or s.get("name") or ""
        )
        izena = self.garbitu_izenburua(izena)
        if not izena:
            return None

        # Datak
        hasiera_str = (
            s.get("dateStart") or s.get("fechaInicio")
            or s.get("startDate") or ""
        )
        bukaera_str = (
            s.get("dateEnd") or s.get("fechaFin")
            or s.get("endDate") or ""
        )
        hasiera_data = self._normalizatu_data(hasiera_str)
        bukaera_data = self._normalizatu_data(bukaera_str)

        # Lekua
        lekua = {
            "non": self.garbitu_testua(
                s.get("placeName_eu") or s.get("placeName") or s.get("lugar") or ""
            ),
            "herria": self.garbitu_testua(
                s.get("municipalityName_eu") or s.get("municipalityName")
                or s.get("municipio") or ""
            ),
            "herrialdea": self.garbitu_testua(
                s.get("provinceName_eu") or s.get("provinceName")
                or s.get("provincia") or ""
            ),
            "koordenatuak": self._lortu_koordenatuak(s),
        }

        # Prezioa
        prezio_str = s.get("price") or s.get("precio") or ""
        prezioa = self.garbitu_prezioa(str(prezio_str) if prezio_str else "")

        # Azalpena
        azalpena = self.garbitu_testua(
            s.get("documentDescription_eu") or s.get("documentDescription")
            or s.get("descripcion") or ""
        )
        azalpena = re.sub(r"<[^>]+>", "", azalpena)[:800]

        # URL eta irudia
        url = s.get("documentUrl") or s.get("url") or s.get("enlace") or ""
        irudi_url = s.get("imageUrl") or s.get("imagen") or s.get("image") or ""

        # Hizkuntza
        hizkuntza = (s.get("documentLanguage") or s.get("idioma") or "").lower()
        if hizkuntza in ("eu", "euskera", "euskara"):
            hizkuntza = "eu"
        elif hizkuntza in ("es", "castellano", "español"):
            hizkuntza = "es"

        # Mota (normalizatu gabe hemen — normalizer.py-k egingo du)
        mota = self.garbitu_testua(
            s.get("eventType_eu") or s.get("eventType")
            or s.get("tipoEvento") or ""
        )

        return {
            "ekitaldia": izena,
            "azalpena": azalpena,
            "mota": mota,
            "hizkuntza": hizkuntza,
            "hasiera_data": hasiera_data,
            "bukaera_data": bukaera_data,
            "lekua": lekua,
            "prezioa": prezioa,
            "url": url,
            "irudiaren_url": irudi_url,
            "iturria": "kulturklik.eus",
            "etiketak": [],
            "nabarmendua": "0",
        }

    # ------------------------------------------------------------------
    # 2. METODOA: HTML scraping (fallback)
    # ------------------------------------------------------------------

    def _html_bidez(self) -> list[dict]:
        """HTML scraping: datozen 30 egunetako ekitaldiak."""
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
                # Erakusketen txartela baztertu
                mota_el = karta.select_one(".event-type, span.type")
                if mota_el:
                    mota_txt = mota_el.get_text().strip().lower()
                    if mota_txt in self.baztertu_kategoriak:
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

        # Mota — erakusketak baztertu
        mota_el = soup.select_one(".event-type")
        mota = self.garbitu_testua(mota_el.get_text() if mota_el else "")
        if mota.lower() in self.baztertu_kategoriak:
            return None

        # Data eta ordua
        hasiera_data = egun.strftime("%Y-%m-%d")
        ordu_el = soup.find(string=re.compile(r"Ordutegia|Horario", re.I))
        if ordu_el and ordu_el.parent:
            ordu_ondoan = ordu_el.parent.find_next_sibling()
            if ordu_ondoan:
                ordu_bat = re.search(r"(\d{1,2}):(\d{2})", ordu_ondoan.get_text())
                if ordu_bat:
                    hasiera_data = egun.replace(
                        hour=int(ordu_bat.group(1)),
                        minute=int(ordu_bat.group(2)),
                        second=0, microsecond=0
                    ).isoformat()

        # Lekua
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

        # Prezioa
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
    def _normalizatu_data(data_str: str) -> str:
        if not data_str:
            return ""
        data_str = str(data_str).strip()
        # ISO formatua: 2026-06-05 edo 2026-06-05T19:30:00
        try:
            return datetime.fromisoformat(data_str).isoformat()
        except ValueError:
            pass
        # dd/mm/yyyy formatua
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", data_str)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return data_str

    @staticmethod
    def _lortu_koordenatuak(s: dict) -> list:
        lat = s.get("latitude") or s.get("latitud") or s.get("lat")
        lon = s.get("longitude") or s.get("longitud") or s.get("lon")
        if lat and lon:
            try:
                return [float(lat), float(lon)]
            except (ValueError, TypeError):
                pass
        return []
