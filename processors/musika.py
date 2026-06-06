"""
musika.py
Musika ekitaldien izenburuak formateatu:
  1. Talde-izenak: DENA MAIUSKULAZ → Title Case
     (baina laburdurak eta sigla motzak utzi maiuskulaz: DJ, MC, BBK...)
  2. '+' loturak → ', ' eta azkenekoa 'eta'
     "Taldea A + Taldea B + Taldea C" → "Taldea A, Taldea B eta Taldea C"
"""

import re


# Hitz laburrak maiuskulaz utzi (sigla, laburdura, DJ izenak...)
MAIUSKULAZ_UTZI = {
    "DJ", "MC", "BB", "BBK", "BEC", "BBC", "FM", "TV",
    "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII",
}

# Artikulu / preposizio txikiak minuskulaz utzi (talde-izenean erdian badaude)
MINUSKULAZ_UTZI = {
    "de", "del", "la", "el", "los", "las", "y", "e",
    "of", "the", "and",
    "eta", "edo", "ta",
}


def _title_case_eu(testua: str) -> str:
    """
    Euskal/espainiar talde-izenei egokitutako title case.
    - Lehen hitza beti maiuskulaz
    - Gainerakoak: MAIUSKULAZ_UTZI zerrendan badaude, utzi; 
      MINUSKULAZ_UTZI zerrendan badaude, minuskulaz; bestela title case.
    """
    hitzak = testua.split()
    emaitza = []
    for i, hitza in enumerate(hitzak):
        hitza_garbi = hitza.strip("\"'()[]")
        hitza_goi = hitza_garbi.upper()

        if hitza_goi in MAIUSKULAZ_UTZI:
            # Sigla/laburdura: beti maiuskulaz
            emaitza.append(hitza.replace(hitza_garbi, hitza_goi))
        elif i > 0 and hitza_garbi.lower() in MINUSKULAZ_UTZI:
            # Artikulua/preposizioa erdian: minuskulaz
            emaitza.append(hitza.replace(hitza_garbi, hitza_garbi.lower()))
        else:
            # Arrunta: lehen letra maiuskulaz, besteak minuskulaz
            berri = hitza_garbi[0].upper() + hitza_garbi[1:].lower() if hitza_garbi else hitza_garbi
            emaitza.append(hitza.replace(hitza_garbi, berri))
    return " ".join(emaitza)


def _normalizatu_taldeak(izena: str) -> str:
    """
    '+' bidez lotutako taldeak ', ' eta 'eta' bihurtu.
    "A + B + C" → "A, B eta C"
    "A + B"     → "A eta B"
    """
    # '+' baten inguruko zuriuneak normalizatu eta zatitu
    zatiak = [z.strip() for z in re.split(r"\s*\+\s*", izena) if z.strip()]

    if len(zatiak) == 1:
        return zatiak[0]
    if len(zatiak) == 2:
        return f"{zatiak[0]} eta {zatiak[1]}"
    # 3+: azkena 'eta'-rekin, besteak koma
    return ", ".join(zatiak[:-1]) + f" eta {zatiak[-1]}"


def _dena_maiuskulaz(testua: str) -> bool:
    """
    True bada testua ia dena maiuskulaz idatzita dago
    (puntuazioa eta zenbakiak kenduta).
    """
    letrak = re.sub(r"[^a-zA-ZÁÉÍÓÚÑáéíóúñ]", "", testua)
    if len(letrak) < 3:
        return False
    maiuskulak = sum(1 for c in letrak if c.isupper())
    return maiuskulak / len(letrak) > 0.7


def formateatu_musika_izena(izena: str) -> str:
    """
    Musika ekitaldi baten izenburua formateatu.
    Bi urrats:
      1. MAIUSKULAK → Title Case (beharrezkoa bada)
      2. '+' → ', ' eta 'eta'
    """
    if not izena:
        return izena

    # Izenburuaren zati nagusia eta parentesi arteko zatia bereizi
    # adib: "KORRONTZI: MUNDUA DANTZAN (Bilbao BBK Live)"
    # Parentesi artekoak ez ukitu title case-rako
    parentesi = re.findall(r"\([^)]*\)", izena)
    izena_clean = re.sub(r"\([^)]*\)", "", izena).strip()

    # Title case beharrezkoa bada
    if _dena_maiuskulaz(izena_clean):
        izena_clean = _title_case_eu(izena_clean)

    # '+' → ', eta'
    izena_clean = _normalizatu_taldeak(izena_clean)

    # Parentesiak berriro gehitu
    if parentesi:
        izena_clean = izena_clean + " " + " ".join(parentesi)

    return izena_clean.strip()
