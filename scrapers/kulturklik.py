"""
kulturklik.py
Kulturklik ekitaldiak Open Data Euskadi JSON deskargatik lortu.

Estrategia:
  1. JSON deskarga (opendata.euskadi.eus)
  2. Fallback: HTML scraping (30 egun)

JSON fitxategiko eremu izenak ez dira ezagunak aldez aurretik,
beraz eremu posible guztiak saiatzen dira (`_atera` metodoa).
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
        erantzuna = self.eskatu(self.json_url)
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

        # DEBUG: lehen sarreraren eremu izenak log egin
        self.logger.info("JSON eremu izenak: %s", list(datuak[0].keys()))

        gaur = datetime.today().date()
        ekitaldiak = []
        for sarrera in datuak:
            # Erakusketak baztertu
            mota_raw = self._atera(sarrera, [
                "eventType", "eventType_eu", "tipoEvento", "type", "tipo", "category"
            ])
            if mota_raw.lower() in self.baztertu_kategoriak:
                continue

            # Iraganeko ekitaldiak baztertu
            data_str = self._atera(sarrera, [
                "dateStart", "dateStart_eu", "fechaInicio", "startDate",
                "date", "fecha", "start", "eventDate"
            ])
            if data_str:
                try:
                    data = datetime.fromisoformat(str(data_str)[:10]).date()
                    if data < gaur:
                        continue
                except (ValueError, TypeError):
                    pass

            ekitaldia = self._bihurtu_sarrera(sarrera)
            if ekitaldia:
                ekitaldiak.append(ekitaldia)

        self.logger.info("Kulturklik JSON: %d ekitaldi", len(ekitaldiak))
        return ekitaldiak

    def _bihurtu_sarrera(self, s: dict) -> dict | None:
        # Izenburua
        izena = self.garbitu_izenburua(self._atera(s, [
            "documentName_eu", "documentName", "name_eu", "name",
            "nombre_eu", "nombre", "title_eu", "title", "izena", "summary"
        ]))
        if not izena:
            return None

        # Datak
        hasiera_str = self._atera(s, [
            "dateStart", "dateStart_eu", "fechaInicio", "startDate",
            "date", "fecha", "start", "eventDate", "hasiera"
        ])
        bukaera_str = self._atera(s, [
            "dateEnd", "dateEnd_eu", "fechaFin", "endDate",
            "end", "bukaera", "finDate"
        ])
        hasiera_data = self._normalizatu_data(hasiera_str)
        bukaera_data = self._normalizatu_data(bukaera_str)

        # Lekua
        lekua = {
            "non": self.garbitu_testua(self._atera(s, [
                "placeName_eu", "placeName", "lugar_eu", "lugar",
                "venue", "location", "lekua", "place", "sala", "recinto"
            ])),
            "herria": self.garbitu_testua(self._atera(s, [
                "municipalityName_eu", "municipalityName", "municipio_eu",
                "municipio", "city", "ciudad", "herria", "town", "locality"
            ])),
            "herrialdea": self.garbitu_testua(self._atera(s, [
                "provinceName_eu", "provinceName", "provincia_eu",
                "provincia", "territory", "herrialdea", "region"
            ])),
            "koordenatuak": self._lortu_koordenatuak(s),
        }

        # Prezioa
        prezio_str = self._atera(s, [
            "price", "precio", "prix", "prezioa", "cost", "admission"
        ])
        prezioa = self.garbitu_prezioa(str(prezio_str) if prezio_str else "")

        # Azalpena
        azalpena = self.garbitu_testua(self._atera(s, [
            "documentDescription_eu", "documentDescription",
            "description_eu", "description", "descripcion_eu",
            "descripcion", "azalpena", "summary", "abstract"
        ]))
        azalpena = re.sub(r"<[^>]+>", "", azalpena)[:800]

        # URL
        url = self._atera(s, [
            "documentUrl", "url", "enlace", "link", "href", "eventUrl"
        ])

        # Irudia
        irudi_url = self._atera(s, [
            "imageUrl", "imagen", "image", "photo", "thumbnail",
            "irudia", "img", "picture", "foto"
        ])

        # Hizkuntza
        hizkuntza_raw = self._atera(s, [
            "documentLanguage", "idioma", "language", "lang", "hizkuntza"
        ]).lower()
        if hizkuntza_raw in ("eu", "euskera", "euskara", "basque"):
            hizkuntza = "eu"
        elif hizkuntza_raw in ("es", "castellano", "español", "spanish"):
            hizkuntza = "es"
        else:
            hizkuntza = hizkuntza_raw

        # Mota
        mota = self.garbitu_testua(self._atera(s, [
            "eventType_eu", "eventType", "tipoEvento_eu", "tipoEvento",
            "type", "tipo", "category", "categoria", "mota"
        ]))

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
    def _atera(sarrera: dict, gakoak: list[str]) -> str:
        """Eremu posible askoren artetik lehena itzuli."""
        for gako in gakoak:
            balioa = sarrera.get(gako)
            if balioa is not None and str(balioa).strip():
                return str(balioa).strip()
        return ""

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
        return data_str

    @staticmethod
    def _lortu_koordenatuak(s: dict) -> list:
        for lat_key, lon_key in [("latitude", "longitude"), ("lat", "lon"), ("latitud", "longitud")]:
            lat = s.get(lat_key)
            lon = s.get(lon_key)
            if lat and lon:
                try:
                    return [float(lat), float(lon)]
                except (ValueError, TypeError):
                    pass
        return []
