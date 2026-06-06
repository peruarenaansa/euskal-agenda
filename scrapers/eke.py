"""
eke.py
EKE (Euskal Kultur Erakundea) agendako ekitaldiak lortu.

EKE Plone 6 CMS erabiltzen du. Bi metodo saiatzen dira:
  1. Plone REST API (@search endpoint) → JSON
  2. HTML scraping (fallback)

Lehen exekuzioan biak saiatuko ditu eta funtzionatzen duena erabiliko du.
"""
import re
import yaml
from datetime import datetime, date
from pathlib import Path

from scrapers.base_scraper import BaseScraper

CONFIG_PATH = Path(__file__).parent.parent / "config" / "iturriak.yml"

# Plone REST API URL ezberdinak, probatu ordenan
PLONE_API_URLS = [
    "https://www.eke.eus/++api++/eu/@search?portal_type=Event&b_size=500&sort_on=start&sort_order=ascending",
    "https://www.eke.eus/++api++/@search?portal_type=Event&b_size=500&sort_on=start",
    "https://www.eke.eus/eu/@search?portal_type=Event&b_size=500",
    "https://www.eke.eus/@search?portal_type=Event&b_size=500",
]

# HTML agenda URL ezberdinak, fallback gisa
HTML_URLS = [
    "https://www.eke.eus/eu/agenda",
    "https://www.eke.eus/eu/kulturaren-berri/agenda",
    "https://www.eke.eus/eu/agenda/ekitaldiak",
]


class EkeScraper(BaseScraper):
    def __init__(self):
        cfg = yaml.safe_load(CONFIG_PATH.read_text())["iturriak"]["eke"]
        super().__init__("eke", eskaera_tartea=cfg["eskaera_tartea"])

    def lortu_ekitaldiak(self) -> list[dict]:
        # 1. Plone REST API saiatu
        ekitaldiak = self._api_bidez()
        if ekitaldiak:
            return ekitaldiak

        # 2. HTML scraping (fallback)
        self.logger.warning("EKE API huts — HTML scraping saiatzen...")
        return self._html_bidez()

    # ------------------------------------------------------------------
    # 1. Plone REST API
    # ------------------------------------------------------------------

    def _api_bidez(self) -> list[dict]:
        headers = {
            **self.HEADERS,
            "Accept": "application/json",
        }
        for url in PLONE_API_URLS:
            self.logger.info("EKE API: saiatzen %s", url)
            erantzuna = self.eskatu(url)
            if not erantzuna:
                continue
            try:
                data = erantzuna.json()
            except Exception:
                continue

            # Plone itzultzen du: {"@id": ..., "items": [...], "items_total": N}
            sarrerak = data.get("items") or data.get("results") or []
            if not sarrerak:
                self.logger.warning("EKE API: 0 sarrera %s", url)
                continue

            self.logger.info("EKE API: %d sarrera jaso", len(sarrerak))
            gaur = date.today()
            ekitaldiak = []
            for sarrera in sarrerak:
                # Plone REST API-ak sarreraren @id URL-a itzultzen du,
                # baina xehetasunak lortzeko bisitatu behar dugu
                ekitaldia = self._bihurtu_api_sarrera(sarrera, gaur)
                if ekitaldia:
                    ekitaldiak.append(ekitaldia)

            self.logger.info("EKE API: %d ekitaldi (iraganekoak gabe)", len(ekitaldiak))
            return ekitaldiak

        return []

    def _bihurtu_api_sarrera(self, s: dict, gaur: date) -> dict | None:
        izena = self.garbitu_izenburua(s.get("title") or s.get("id") or "")
        if not izena:
            return None

        # Datak — Plone ISO formatuan ematen ditu
        hasiera_str = s.get("start") or s.get("effective") or ""
        bukaera_str = s.get("end") or s.get("expires") or ""
        hasiera_data = self._dt_str(hasiera_str)
        bukaera_data = self._dt_str(bukaera_str)

        # Iraganekoak baztertu
        if hasiera_data:
            try:
                if datetime.fromisoformat(hasiera_data[:10]).date() < gaur:
                    return None
            except ValueError:
                pass

        # Lekua
        leku_str = s.get("location") or ""
        lekua = self._parseatu_lekua_str(leku_str)

        # Azalpena — Plone-k "description" (laburra) eta "text" (HTML osoa) ditu
        azalpena = self.garbitu_testua(s.get("description") or "")
        azalpena = re.sub(r"<[^>]+>", "", azalpena)[:800]

        # URL
        url = s.get("@id") or s.get("url") or ""

        # Irudia — Plone image eremu nagusia
        irudi_url = ""
        irudi = s.get("image") or {}
        if isinstance(irudi, dict):
            irudi_url = irudi.get("download") or irudi.get("scales", {}).get("preview", {}).get("download") or ""

        # Mota
        mota = self.garbitu_testua(
            s.get("Subject") and ", ".join(s["Subject"])
            or s.get("type_title") or ""
        )

        return {
            "ekitaldia": izena,
            "azalpena": azalpena,
            "mota": mota,
            "hizkuntza": "eu",
            "hasiera_data": hasiera_data,
            "bukaera_data": bukaera_data,
            "lekua": lekua,
            "prezioa": {"zenbatekoa": None, "moneta": "EUR", "doan": False},
            "url": url,
            "irudiaren_url": irudi_url,
            "iturria": "eke.eus",
            "etiketak": [],
            "nabarmendua": "0",
        }

    # ------------------------------------------------------------------
    # 2. HTML scraping (fallback)
    # ------------------------------------------------------------------

    def _html_bidez(self) -> list[dict]:
        from bs4 import BeautifulSoup

        for url in HTML_URLS:
            self.logger.info("EKE HTML: saiatzen %s", url)
            erantzuna = self.eskatu(url)
            if not erantzuna:
                continue

            soup = BeautifulSoup(erantzuna.text, "lxml")
            ekitaldiak = []
            gaur = date.today()

            # Plone agenda zerrenda: ekitaldi-karten bilaketa
            kartak = soup.select(
                "article.event, .event-item, li.event, "
                ".cal_item, .vevent, article[class*='event']"
            )
            if not kartak:
                # Lotura orokorrak bilatu
                kartak = soup.select("main a[href*='/ekitaldia'], main a[href*='/event'], main a[href*='/agenda/']")

            self.logger.info("EKE HTML: %d karta aurkitu", len(kartak))
            ikusi_urlak = set()

            for karta in kartak:
                lotura = karta if karta.name == "a" else karta.select_one("a[href]")
                if not lotura:
                    continue
                ekitaldi_url = lotura.get("href", "")
                if not ekitaldi_url:
                    continue
                if not ekitaldi_url.startswith("http"):
                    ekitaldi_url = "https://www.eke.eus" + ekitaldi_url
                if ekitaldi_url in ikusi_urlak:
                    continue
                ikusi_urlak.add(ekitaldi_url)

                # Data karta berean badago, erabili
                data_el = karta.select_one("time[datetime], .event-date, .date")
                data_str = ""
                if data_el:
                    data_str = data_el.get("datetime") or data_el.get_text().strip()

                izena_el = karta.select_one("h2, h3, h4, .event-title, strong")
                izena = self.garbitu_izenburua(
                    izena_el.get_text() if izena_el else lotura.get_text()
                )
                if not izena:
                    continue

                ekitaldiak.append({
                    "ekitaldia": izena,
                    "azalpena": "",
                    "mota": "",
                    "hizkuntza": "eu",
                    "hasiera_data": self._dt_str(data_str),
                    "bukaera_data": "",
                    "lekua": {"non": "", "herria": "", "herrialdea": "", "koordenatuak": []},
                    "prezioa": {"zenbatekoa": None, "moneta": "EUR", "doan": False},
                    "url": ekitaldi_url,
                    "irudiaren_url": "",
                    "iturria": "eke.eus",
                    "etiketak": [],
                    "nabarmendua": "0",
                })

            if ekitaldiak:
                self.logger.info("EKE HTML: %d ekitaldi lortu", len(ekitaldiak))
                return ekitaldiak

        self.logger.error("EKE: metodo guztiek huts egin dute")
        return []

    # ------------------------------------------------------------------
    # Laguntzaileak
    # ------------------------------------------------------------------

    @staticmethod
    def _dt_str(data_raw) -> str:
        if not data_raw:
            return ""
        data_str = str(data_raw).strip()
        try:
            return datetime.fromisoformat(data_str).isoformat()
        except ValueError:
            pass
        # dd/mm/yyyy
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", data_str)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return data_str

    @staticmethod
    def _parseatu_lekua_str(leku_str: str) -> dict:
        zatiak = [z.strip() for z in str(leku_str).split(",") if z.strip()]
        return {
            "non": zatiak[0] if zatiak else "",
            "herria": zatiak[-1] if len(zatiak) > 1 else "",
            "herrialdea": "",
            "koordenatuak": [],
        }
