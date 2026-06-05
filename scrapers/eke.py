"""
eke.py
EKE (Euskal Kultur Erakundea) agendako ekitaldiak iCal formatuan lortu.
URL: https://www.eke.eus/events/aggregator/@@event_listing_ical?mode=future
"""
import re
import yaml
from datetime import datetime
from pathlib import Path

from icalendar import Calendar

from scrapers.base_scraper import BaseScraper

CONFIG_PATH = Path(__file__).parent.parent / "config" / "iturriak.yml"


class EkeScraper(BaseScraper):
    def __init__(self):
        cfg = yaml.safe_load(CONFIG_PATH.read_text())["iturriak"]["eke"]
        super().__init__("eke", eskaera_tartea=cfg["eskaera_tartea"])
        self.ical_url = cfg["ical_url"]

    def lortu_ekitaldiak(self) -> list[dict]:
        self.logger.info("EKE: iCal fitxategia deskargatzen...")
        erantzuna = self.eskatu(self.ical_url)
        if not erantzuna:
            return []
        try:
            egutegi = Calendar.from_ical(erantzuna.content)
        except Exception as e:
            self.logger.error("iCal parseaketa huts: %s", e)
            return []

        ekitaldiak = []
        for osagaia in egutegi.walk():
            if osagaia.name != "VEVENT":
                continue
            ekitaldia = self._parseatu_vevent(osagaia)
            if ekitaldia:
                ekitaldiak.append(ekitaldia)

        self.logger.info("EKE: %d ekitaldi lortu", len(ekitaldiak))
        return ekitaldiak

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
