"""
normalizer.py
Datuak normalizatu:
  - Herri eta antzoki izenak euskaratu
  - Kategoriak 9 mota ofizialetara mapatu (+ bestelakoak)
  - Herrialdea inferitu
  - ID bakarra sortu
"""
import hashlib
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "normalizazioa.yml"

# Agendako mota ofizialak
MOTA_ONARTUAK = {
    "antzerkia",
    "dantza",
    "ikus-entzunezkoak",
    "musika",
    "hitzaldiak",
    "bertsolaritza",
    "erakusketak",
    "haur-jarduera",
    "ikastaroak",
    "bestelakoak",
}


class Normalizatzailea:
    def __init__(self):
        cfg = yaml.safe_load(CONFIG_PATH.read_text())
        self.herriak = cfg.get("herriak", {})
        self.antzokiak = cfg.get("antzokiak", {})
        self.herriak_herrialdeak = cfg.get("herriak_herrialdeak", {})
        self.kategoriak = cfg.get("kategoriak", {})

    def normalizatu(self, ekitaldia: dict) -> dict:
        lekua = ekitaldia.get("lekua", {})
        lekua["herria"] = self._normalizatu_herria(lekua.get("herria", ""))
        lekua["non"] = self._normalizatu_antzokia(lekua.get("non", ""))
        lekua["herrialdea"] = self._inferitu_herrialdea(
            lekua["herria"], lekua.get("herrialdea", "")
        )
        ekitaldia["lekua"] = lekua
        ekitaldia["mota"] = self._normalizatu_mota(ekitaldia.get("mota", ""))
        ekitaldia["id"] = self._sortu_id(
            ekitaldia.get("iturria", ""),
            ekitaldia.get("url", ""),
            ekitaldia.get("ekitaldia", ""),
            ekitaldia.get("hasiera_data", ""),
        )
        return ekitaldia

    def normalizatu_guztiak(self, ekitaldiak: list[dict]) -> list[dict]:
        return [self.normalizatu(e) for e in ekitaldiak]

    # ------------------------------------------------------------------

    def _normalizatu_herria(self, herria: str) -> str:
        herria = herria.strip()
        if herria in self.herriak:
            return self.herriak[herria]
        for zahar, berri in self.herriak.items():
            if herria.lower() == zahar.lower():
                return berri
        return herria

    def _normalizatu_antzokia(self, izena: str) -> str:
        izena = izena.strip()
        if izena in self.antzokiak:
            return self.antzokiak[izena]
        for zahar, berri in self.antzokiak.items():
            if izena.lower() == zahar.lower():
                return berri
        return izena

    def _inferitu_herrialdea(self, herria: str, existentea: str) -> str:
        if existentea:
            return existentea
        return self.herriak_herrialdeak.get(herria, "")

    def _normalizatu_mota(self, mota: str) -> str:
        """
        Mota bat agendako 9 kategoria ofizialetara mapatu.
        Ezagutzen ez bada: 'bestelakoak'.
        """
        mota = mota.strip()

        # Zuzeneko bilaketa
        if mota in self.kategoriak:
            emaitza = self.kategoriak[mota]
            return emaitza if emaitza in MOTA_ONARTUAK else "bestelakoak"

        # Maiuskulaz berdin
        for zahar, berri in self.kategoriak.items():
            if mota.lower() == zahar.lower():
                return berri if berri in MOTA_ONARTUAK else "bestelakoak"

        # Jatorrizko balioa dagoeneko onartua bada, utzi
        if mota.lower() in MOTA_ONARTUAK:
            return mota.lower()

        # Ezezaguna → bestelakoak
        return "bestelakoak"

    @staticmethod
    def _sortu_id(iturria: str, url: str, izena: str, data: str) -> str:
        gakoa = f"{iturria}|{url}|{izena}|{data}"
        return hashlib.sha256(gakoa.encode()).hexdigest()[:8]
