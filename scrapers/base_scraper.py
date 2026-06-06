"""
base_scraper.py — Scraper guztien oinarrizko klasea.
Retry logika, rate limiting eta testuen garbiketa.

Eskaera estrategia:
  1. requests (azkar, ohiko guneetarako)
  2. curl subprocess (requests huts egiten badu — TLS eta firewall arazoetarako)
"""
import html
import json
import logging
import re
import subprocess
import time
from abc import ABC, abstractmethod
from io import BytesIO

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class _FakeResponse:
    """curl emaitza requests.Response moduan erabiltzeko."""
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.text = content.decode("utf-8", errors="replace")
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class BaseScraper(ABC):
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "eu, es;q=0.8, en;q=0.5",
        "Accept": "application/json, text/html, */*",
    }
    # Timeout segundoak: (konexioa, irakurketa)
    TIMEOUT = (30, 60)

    def __init__(self, iturria_izena: str, eskaera_tartea: float = 2.0):
        self.iturria_izena = iturria_izena
        self.eskaera_tartea = eskaera_tartea
        self.logger = logging.getLogger(iturria_izena)
        self._azken_eskaera = 0.0

    def eskatu(self, url: str, curl_lehentasuna: bool = False, **kwargs):
        """
        GET eskaera rate limiting eta retry-rekin.
        curl_lehentasuna=True bada, curl erabiltzen du requests baino lehen.
        """
        igaro = time.time() - self._azken_eskaera
        if igaro < self.eskaera_tartea:
            time.sleep(self.eskaera_tartea - igaro)

        metodoak = (
            [self._eskatu_curl, self._eskatu_requests]
            if curl_lehentasuna
            else [self._eskatu_requests, self._eskatu_curl]
        )

        for saiakera in range(3):
            for metodo in metodoak:
                try:
                    erantzuna = metodo(url, **kwargs)
                    if erantzuna and erantzuna.ok:
                        self._azken_eskaera = time.time()
                        return erantzuna
                except Exception as e:
                    self.logger.debug("%s huts (%d/3): %s — %s",
                                      metodo.__name__, saiakera + 1, url, e)

            if saiakera < 2:
                itxaron = 10 * (saiakera + 1)
                self.logger.warning("Saiakera %d/3 huts, %ds itxaroten: %s",
                                    saiakera + 1, itxaron, url)
                time.sleep(itxaron)

        self.logger.error("Eskaera guztiz huts: %s", url)
        return None

    def _eskatu_requests(self, url: str, **kwargs):
        return requests.get(
            url, headers=self.HEADERS, timeout=self.TIMEOUT, **kwargs
        )

    def _eskatu_curl(self, url: str, **kwargs) -> _FakeResponse | None:
        """curl subprocess bidez — requests huts egiten duenean."""
        try:
            cmd = [
                "curl", "--silent", "--fail", "--location",
                "--max-time", "60",
                "--connect-timeout", "30",
                "--compressed",
                "-H", f"User-Agent: {self.HEADERS['User-Agent']}",
                "-H", f"Accept-Language: {self.HEADERS['Accept-Language']}",
                "-H", f"Accept: {self.HEADERS['Accept']}",
                url,
            ]
            emaitza = subprocess.run(
                cmd, capture_output=True, timeout=70
            )
            if emaitza.returncode == 0 and emaitza.stdout:
                return _FakeResponse(emaitza.stdout, 200)
            self.logger.debug("curl %d: %s", emaitza.returncode, url)
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            self.logger.debug("curl ezin erabili: %s", e)
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

        # "Entradas" hitza kendu hasieran
        izena = re.sub(r'^entradas\s*["\u201c]?\s*', '', izena, flags=re.IGNORECASE).strip()

        # "Programa" hitza kendu hasieran
        izena = re.sub(r'^programa\s+', '', izena, flags=re.IGNORECASE).strip()

        # DENA MAIUSKULAZ → Title Case (+ konbertsioa baino lehen)
        if izena == izena.upper() and len(izena) > 3:
            izena = izena.title()

        # '+' bidezko talde-izenak bateratu
        from processors.musika import _normalizatu_taldeak
        izena = _normalizatu_taldeak(izena)

        # Urtea kendu amaieran (2020-2099)
        izena = re.sub(r'\s+20[2-9]\d\s*$', '', izena).strip()

        izena = izena.rstrip(".,;:")
        izena = re.sub(r'^["\'](.+)["\']$', r"\1", izena)
        izena = BaseScraper._garbitu_izenburu_elebitua(izena)
        return izena

    @staticmethod
    def _garbitu_izenburu_elebitua(izena: str) -> str:
        """
        Elebiko edo soberakiko tituluetatik euskarazko zatia atera.

        Kasuak:
          'Ciclo "Compartir Saberes / Ezagutzak Partekatuz" 2026'
              → 'Ezagutzak Partekatuz 2026'
          'Ciclo de conferencias "Mirande, hasiera berri bat"'
              → 'Mirande, hasiera berri bat'
          '"Gazte Artea Ezkerraldean 2026" (Santurtzi)'
              → 'Gazte Artea Ezkerraldean 2026'
          'Certamen de Poesía Ernestina de Champourcín 2026'
              → '' (gaztelaniaz soilik → hizkuntza.py-k baztertuko du)
        """
        # Gaztelaniako hitz adierazgarriak (izenburu hasieran agertzen direnak)
        GAZT_HASIERA = re.compile(
            r"^(ciclo|certamen|concurso|jornada[s]?|curso|encuentro|"
            r"festival|feria|semana|muestra|exposici[oó]n|concierto|"
            r"conferencia|taller|programa|proyecto|convocatoria|concurs)\b",
            re.IGNORECASE,
        )

        # 1. " / " batekin bereizitako bi aldeak: bigarrena hartu
        if " / " in izena:
            zatiak = [z.strip() for z in izena.split(" / ")]
            if len(zatiak) == 2:
                urtea_m = re.search(r'\b(20\d{2})\b', izena)
                bigarrena = zatiak[1].strip()
                # Komatxo mota guztiak kendu (hasieran, amaieran, eta urtearen aurretik)
                bigarrena = re.sub(r'["\'\\\u201c\u201d\u00ab\u00bb]', '', bigarrena).strip()
                if bigarrena:
                    izena = bigarrena
                    if urtea_m and urtea_m.group() not in izena:
                        izena = f"{izena} {urtea_m.group()}"

        # 2. Gaztelaniazko testuinguruan komatxo arteko zatia hartu
        #    'Ciclo de conferencias "Mirande, hasiera berri bat"' → 'Mirande...'
        if GAZT_HASIERA.match(izena):
            komatxoak = re.findall(r'["\u201c\u00ab]([^"\u201d\u00bb]{4,})["\u201d\u00bb]', izena)
            if komatxoak:
                urtea = re.search(r'\b(20\d{2})\b', izena)
                izena = komatxoak[-1].strip()  # Azken komatxo-zatia (normalean euskarazkoa)
                if urtea and urtea.group() not in izena:
                    izena = f"{izena} {urtea.group()}"

        # 3. Parentesi arteko herri-izenak kendu amaieran
        #    "(Santurtzi)", "(Bilbao)"... → kendu
        izena = re.sub(
            r'\s*\([A-ZÁÉÍÓÚÑ][a-záéíóúñA-ZÁÉÍÓÚÑ\s\-]{2,30}\)\s*$',
            '',
            izena,
        ).strip()

        # 4. Komatxo eta kontraslash soberakinak kendu hasieran/amaieran
        izena = re.sub(r'^[\s"\'\\]+|[\s"\'\\]+$', '', izena).strip()

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
