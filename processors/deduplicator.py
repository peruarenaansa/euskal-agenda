"""
deduplicator.py — Bikoiztunak kendu.
Irizpideak:
  1. ID berdina (URL + data berdinetik), EDO
  2. Izen antzekoa (>85%) + data berdina + herri berdina
"""
import re
from difflib import SequenceMatcher


def kendu_bikoiztunak(ekitaldiak: list[dict]) -> list[dict]:
    emaitza = []
    ikusi_idak = set()

    for ekitaldia in ekitaldiak:
        eid = ekitaldia.get("id", "")
        if eid and eid in ikusi_idak:
            continue

        izena = _normalizatu(ekitaldia.get("ekitaldia", ""))
        data = ekitaldia.get("hasiera_data", "")[:10]
        herria = ekitaldia.get("lekua", {}).get("herria", "").lower()

        bikoiztua = any(
            data == ex.get("hasiera_data", "")[:10]
            and herria == ex.get("lekua", {}).get("herria", "").lower()
            and SequenceMatcher(None, izena, _normalizatu(ex.get("ekitaldia", ""))).ratio() > 0.85
            for ex in emaitza
        )

        if not bikoiztua:
            emaitza.append(ekitaldia)
            if eid:
                ikusi_idak.add(eid)

    return emaitza


def _normalizatu(testua: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", testua.lower())).strip()
