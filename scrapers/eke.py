"""
eke.py
EKE (Euskal Kultur Erakundea) agendako ekitaldiak iCal formatuan lortu.
URL alternatiboak saiatzen dira, Plone CMS erabiltzen baitu EKE-k.
"""
import re
import yaml
from datetime import datetime
from pathlib import Path

from icalendar import Calendar

from scrapers.base_scraper import BaseScraper

CONFIG_PATH = Path(__file__).parent.parent / "config" / "iturriak.yml"

# Plone CMS iCal URL formatuak, probatu ordenan
ICAL_URLS = [
    "https://www.eke.eus/events/aggregator/@@event_listing_ical?mode=future",
    "https://www.eke.eus/eu/agenda/@@event_listing_ical?mode=future",
    "https://www.eke.eus/eu/agenda/@@eventsfolder_ical_view",
    "https://www.eke.eus/eu/agenda/@@icalendar_view",
    "https://www.eke.eus/eu/kulturaren-berri/agenda/@@event_listing_ical?mode=future",
    "https://www.eke.eus/@@event_listing_ical?mode=future",
]


class EkeScraper(BaseScraper):
    def __init__(self):
        cfg = yaml.safe_load(CONFIG_PATH.read_text())["iturriak"]["eke"]
        super().__init__("eke", eskaera_tartea=cfg["eskaera_tartea"])
        self.ical_url = cfg["ical_url"]

    def lortu_ekitaldiak(self) -> list[dict]:
        # Config-ko URLa lehenik, gero alternatiboak
        urls = [self.ical_url] + [u for u in ICAL_URLS if u != self.ical_url]

        for url in urls:
            self.logger.info("EKE: saiatzen %s", url)
            erantzuna = self.eskatu(url)
            if not erantzuna:
                continue
            # iCal formatua egiaztatu
            if b"BEGIN:VCALENDAR" not in erantzuna.content[:100]:
                self.logger.warning("EKE: %s ez da iCal formatua", url)
                continue
            try:
                egutegi = Calendar.from_ical(erantzuna.content)
            except Exception as e:
                self.logger.error("iCal parseaketa huts: %s", e)
                continue

            ekitaldiak = []
            for osagaia in egutegi.walk():
                if osagaia.name != "VEVENT":
                    continue
                ekitaldia = self._parseatu_vevent(osagaia)
                if ekitaldia:
                    ekitaldiak.append(ekitaldia)

            if ekitaldiak:
                self.logger.info("EKE: %d ekitaldi lortu (%s)", len(ekitaldiak), url)
                return ekitaldiak
            self.logger.warning("EKE: %s-tik 0 ekitaldi", url)

        self.logger.error("EKE: URL guztiak huts egin dute")
        return []

    def _parseatu_vevent(self, gertakaria) -> dict | None:
        def prop(gakoa):
            balioa = gertakaria.get(gakoa)
            return self.garbitu_testua(str(balioa)) if balioa is not None else ""

        izena = self.garbitu_izenburua(prop("SUMMARY"))
        if not izena:
            return None

        hasiera_data = self._dt_str(gertakaria.get("DTSTART"))
        bukaera_data = self._dt_str(gertakaria.get("DTEND"))

        leku_str = prop("LOCATION")
        lekua = self._parseatu_lekua_str(leku_str)

        azalpena = prop("DESCRIPTION")
        azalpena = re.sub(r"<[^>]+>", "", azalpena)[:800]

        kategoriak_raw = gertakaria.get("CATEGORIES")
        mota = ""
        if kategoriak_raw:
            if hasattr(kategoriak_raw, "cats"):
                mota = ", ".join(str(c) for c in kategoriak_raw.cats)
            else:
                mota = str(kategoriak_raw)
            mota = self.garbitu_testua(mota)

        return {
            "ekitaldia": izena,
            "azalpena": azalpena,
            "mota": mota,
            "hizkuntza": "eu",
            "hasiera_data": hasiera_data,
            "bukaera_data": bukaera_data,
            "lekua": lekua,
            "prezioa": {"zenbatekoa": None, "moneta": "EUR", "doan": False},
            "url": prop("URL"),
            "irudiaren_url": "",
            "iturria": "eke.eus",
            "etiketak": [],
            "nabarmendua": "0",
        }

    @staticmethod
    def _dt_str(dt_prop) -> str:
        if not dt_prop:
            return ""
        dt = dt_prop.dt
        return dt.isoformat() if isinstance(dt, datetime) else dt.isoformat()

    @staticmethod
    def _parseatu_lekua_str(leku_str: str) -> dict:
        zatiak = [z.strip() for z in leku_str.split(",") if z.strip()]
        return {
            "non": zatiak[0] if zatiak else "",
            "herria": zatiak[-1] if len(zatiak) > 1 else "",
            "herrialdea": "",
            "koordenatuak": [],
        }
