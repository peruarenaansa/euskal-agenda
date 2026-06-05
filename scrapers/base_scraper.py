"""
base_scraper.py — Scraper guztien oinarrizko klasea.
Retry logika, rate limiting eta testuen garbiketa.
"""
import html
import logging
import re
import time
from abc import ABC, abstractmethod

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class BaseScraper(ABC):
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; EuskalAgenda/1.0; "
            "+https://github.com/zure-erabiltzailea/euskal-agenda)"
        ),
        "Accept-Language": "eu, es;q=0.8",
        "Accept": "application/json, text/html, */*",
    }

    def __init__(self, iturria_izena: str, eskaera_tartea: float = 2.0):
        self.iturria_izena = iturria_izena
        self.eskaera_tartea = eskaera_tartea
        self.logger = logging.getLogger(iturria_izena)
        self._azken_eskaera = 0.0

    def eskatu(self, url: str, **kwargs) -> requests.Response | None:
        """GET eskaera rate limiting eta 3 retry-rekin."""
        igaro = time.time() - self._azken_eskaera
        if igaro < self.eskaera_tartea:
            time.sleep(self.eskaera_tartea - igaro)
        for saiakera in range(3):
            try:
                erantzuna = requests.get(url, headers=self.HEADERS, timeout=20, **kwargs)
                self._azken_eskaera = time.time()
                erantzuna.raise_for_status()
                return erantzuna
            except requests.RequestException as e:
                self.logger.warning("Eskaera huts (%d/3): %s — %s", saiakera + 1, url, e)
                if saiakera < 2:
                    time.sleep(5 * (saiakera + 1))
        self.logger.error("Eskaera guztiz huts: %s", url)
        return None

    # ------------------------------------------------------------------
    # Testu-garbiketa (iturri guztietan erabiltzeko)
    # ------------------------------------------------------------------
    @staticmethod
    def garbitu_testua(testua: str | None) -> str:
        if not testua:
            return ""
        testua = html.unescape(str(testua))
        for zahar, berri in {
            "\u201c": '"', "\u201d": '"',
            "\u2018": "'", "\u2019": "'",
            "\u00ab": '"', "\u00bb": '"',
            "\u2013": "-", "\u2014": "-",
            "\u00a0": " ",
        }.items():
            testua = testua.replace(zahar, berri)
        return re.sub(r"\s+", " ", testua).strip()

    @staticmethod
    def garbitu_izenburua(izena: str | None) -> str:
        if not izena:
            return ""
        izena = BaseScraper.garbitu_testua(izena)
        if izena == izena.upper() and len(izena) > 3:
            izena = izena.title()
        izena = izena.rstrip(".,;:")
        izena = re.sub(r'^["\'](.+)["\']$', r"\1", izena)
        return izena

    @staticmethod
    def garbitu_prezioa(prezioa_str: str | None) -> dict:
        if not prezioa_str:
            return {"zenbatekoa": None, "moneta": "EUR", "doan": False}
        p = BaseScraper.garbitu_testua(prezioa_str).lower()
        if any(h in p for h in ["doa", "gratu", "libre", "free", "gratuit", "0 €", "0€"]):
            return {"zenbatekoa": 0, "moneta": "EUR", "doan": True}
        zenbakiak = re.findall(r"\d+(?:[.,]\d+)?", p)
        if zenbakiak:
            return {"zenbatekoa": float(zenbakiak[0].replace(",", ".")), "moneta": "EUR", "doan": False}
        return {"zenbatekoa": None, "moneta": "EUR", "doan": False}

    @abstractmethod
    def lortu_ekitaldiak(self) -> list[dict]:
        ...
