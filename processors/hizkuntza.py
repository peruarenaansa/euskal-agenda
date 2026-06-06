"""
hizkuntza.py
Ekitaldiak hizkuntzaren arabera iragaztu: euskarazkoak soilik gorde.

Logika:
  1. 'hizkuntza' eremua badago eta argia bada → erabili zuzenean
  2. Eremua ez badago edo ez bada argia → testua aztertu (heuristika)
  3. Hizkuntzarik ezin bada jakin → GORDE (ez baztertu zalantzazkoak)
"""

import re
import logging

logger = logging.getLogger("hizkuntza")

# Hizkuntza-kode onartuak euskararentzat
EUSKARA_KODEAK = {
    "eu", "eus", "euskera", "euskara", "basque", "vasco",
    "eu-eu", "eu_eu", "eu-es",
}

# Hizkuntza-kode baztertutakoak (gaztelania / frantsesa / ingelesa)
BAZTERTU_KODEAK = {
    "es", "spa", "castellano", "español", "spanish", "espagnol",
    "fr", "fra", "français", "frances", "french",
    "en", "eng", "english", "inglés",
    "es-eu", "es_eu", "fr-eu", "fr_eu",
}

# Hitz euskararen adierazleak (testu heuristikarako)
EUSKARA_HITZAK = re.compile(
    r"\b(eta|edo|dela|ditu|dute|dira|den|bat|bi|hiru|lau|bost|"
    r"nahi|dago|daude|da\b|du\b|dut|ditut|dugu|naiz|zara|"
    r"euskal|euskara|bertso|antzerk|kontzer|jaial|hitzaldi|"
    r"ikastaro|tailer|dantza|zinema|erakusk)\b",
    re.IGNORECASE,
)

# Gaztelaniaren adierazleak (ez euskara)
GAZTELANIA_HITZAK = re.compile(
    r"\b(concierto|teatro|exposición|exposicion|festival|entrada|"
    r"espectáculo|espectaculo|actividad|charla|curso|taller es\b|"
    r"presentación|presentacion|conferencia|celebra|organiza)\b",
    re.IGNORECASE,
)

# Frantsesaren adierazleak
FRANTSES_HITZAK = re.compile(
    r"\b(concert|théâtre|theatre|exposition|spectacle|"
    r"conférence|conference|atelier|journée|soirée)\b",
    re.IGNORECASE,
)


def _kodea_sailkatu(kode: str) -> str | None:
    """
    Hizkuntza-kodea sailkatu.
    Itzultzen du: 'eu' | 'ez-eu' | None (ezezaguna)
    """
    kode = kode.strip().lower()
    if not kode:
        return None
    if kode in EUSKARA_KODEAK:
        return "eu"
    if kode in BAZTERTU_KODEAK:
        return "ez-eu"
    # Bi hizkuntza: "eu, es" → hizkuntzetako bat euskara bada, onartu
    zatiak = re.split(r"[,;/\s]+", kode)
    batzuk_eu = any(z in EUSKARA_KODEAK for z in zatiak)
    batzuk_ez = any(z in BAZTERTU_KODEAK for z in zatiak)
    if batzuk_eu:
        return "eu"
    if batzuk_ez:
        return "ez-eu"
    return None


def _testutik_hizkuntza(ekitaldia: dict) -> str | None:
    """
    Testua aztertu eta hizkuntza inferitu.
    Itzultzen du: 'eu' | 'ez-eu' | None (ezezaguna)
    """
    testuak = " ".join(filter(None, [
        ekitaldia.get("ekitaldia", ""),
        ekitaldia.get("azalpena", ""),
    ]))
    if not testuak.strip():
        return None

    eu_hits = len(EUSKARA_HITZAK.findall(testuak))
    es_hits = len(GAZTELANIA_HITZAK.findall(testuak))
    fr_hits = len(FRANTSES_HITZAK.findall(testuak))

    ez_eu_hits = es_hits + fr_hits

    if eu_hits > 0 and eu_hits >= ez_eu_hits:
        return "eu"
    if ez_eu_hits > eu_hits and ez_eu_hits >= 2:
        return "ez-eu"
    return None


def ekitaldia_iragaztu(ekitaldia: dict) -> bool:
    """
    True itzuli ekitaldia gorde behar bada (euskarazkoa edo ezezaguna).
    False itzuli baztertu behar bada (argi gaztelaniaz edo frantsesez).
    """
    kode = ekitaldia.get("hizkuntza", "")
    sailkapena = _kodea_sailkatu(kode)

    if sailkapena == "eu":
        return True
    if sailkapena == "ez-eu":
        return False

    # Kodea ezezaguna → testua aztertu
    sailkapena_testua = _testutik_hizkuntza(ekitaldia)

    if sailkapena_testua == "eu":
        return True
    if sailkapena_testua == "ez-eu":
        return False

    # Ezin jakin → GORDE
    return True


def hizkuntza_iragaztu(ekitaldiak: list[dict]) -> list[dict]:
    """Euskarazkoak eta ezezagunak itzuli; gaztelaniaz/frantsesez daudenak baztertu."""
    emaitza = []
    baztertuta = 0
    for e in ekitaldiak:
        if ekitaldia_iragaztu(e):
            emaitza.append(e)
        else:
            baztertuta += 1
            logger.debug("Baztertuta (%s): %s", e.get("hizkuntza", "?"), e.get("ekitaldia", ""))

    logger.info("Hizkuntza iragazkia: %d baztertuta", baztertuta)
    return emaitza
