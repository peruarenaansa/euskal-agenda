"""
main.py — Euskal Agenda, sarrera-puntu nagusia.

Cron-aren logika:
  - agenda.json badago: dagoeneko gordeak dauden ekitaldiak MANTENDU
    (iraganekoak eta oraindik etortzekoak biak)
  - Iturburuetatik BERRI direnak soilik ekarri (dauden ID-ak ez berriro)
  - Iraganeko ekitaldiak (3 hilabete baino zaharragoak) EZABATU
  - Eguneraketa: ID berriak gehitu + dauden eremuak ez ukitu

Horrela:
  ✓ Prozesua azkar (ekitaldi ezagunak berriz ez bildu)
  ✓ JSON fitxategia gero eta aberatsagoa
  ✓ Iraganeko datu zaharrak ez pilatu
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from scrapers.kulturklik import KulturklikScraper
from scrapers.eke import EkeScraper
from processors.normalizer import Normalizatzailea
from processors.deduplicator import kendu_bikoiztunak

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

DATA_DIR = Path(__file__).parent / "data"
AGENDA_FITXATEGIA = DATA_DIR / "agenda.json"

# Iraganeko ekitaldiak zenbat hilabetetan gorde (3 = hiru hilabete)
IRAGANEKO_HILABETEAK = 3


def kargatu_daudenak() -> dict[str, dict]:
    """
    Dauden agenda.json-etik ekitaldiak kargatu.
    ID → ekitaldia dict gisa itzuli, bilaketa azkarrerako.
    """
    if not AGENDA_FITXATEGIA.exists():
        return {}
    try:
        agenda = json.loads(AGENDA_FITXATEGIA.read_text(encoding="utf-8"))
        ekitaldiak = agenda.get("ekitaldiak", [])
        return {e["id"]: e for e in ekitaldiak if e.get("id")}
    except Exception as e:
        logger.warning("agenda.json kargatzean errorea: %s", e)
        return {}


def iragazki_zaharrak(ekitaldiak: list[dict]) -> list[dict]:
    """
    3 hilabete baino lehenagoko ekitaldiak ezabatu.
    Muga: gaur - IRAGANEKO_HILABETEAK hilabete.
    """
    muga = datetime.now() - timedelta(days=30 * IRAGANEKO_HILABETEAK)
    muga_str = muga.strftime("%Y-%m-%d")

    garbiak = []
    for e in ekitaldiak:
        data = e.get("hasiera_data", "")
        if not data:
            garbiak.append(e)  # Datarik ez → utzi
            continue
        if data[:10] >= muga_str:
            garbiak.append(e)

    kendu = len(ekitaldiak) - len(garbiak)
    if kendu:
        logger.info("Iraganeko ekitaldiak ezabatuta: %d", kendu)
    return garbiak


def egin_scraping() -> list[dict]:
    """Iturri guztietatik ekitaldiak lortu."""
    ekitaldiak = []
    for iturria in [KulturklikScraper(), EkeScraper()]:
        try:
            berri = iturria.lortu_ekitaldiak()
            logger.info("%s: %d ekitaldi jaso", iturria.iturria_izena, len(berri))
            ekitaldiak.extend(berri)
        except Exception as e:
            logger.error("%s: ustekabeko errorea: %s", iturria.iturria_izena, e)
    return ekitaldiak


def gorde_agenda(ekitaldiak: list[dict]):
    """Ekitaldiak JSON formatuan gorde, hasiera dataren arabera ordenatuta."""
    DATA_DIR.mkdir(exist_ok=True)
    ekitaldiak_ordenatua = sorted(
        ekitaldiak,
        key=lambda e: e.get("hasiera_data") or "9999"
    )
    iturriak = sorted({e.get("iturria", "") for e in ekitaldiak_ordenatua})

    agenda = {
        "meta": {
            "noiz_eguneratua": datetime.now(timezone.utc).isoformat(),
            "ekitaldi_kopurua": len(ekitaldiak_ordenatua),
            "iturriak": iturriak,
        },
        "ekitaldiak": ekitaldiak_ordenatua,
    }
    AGENDA_FITXATEGIA.write_text(
        json.dumps(agenda, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("agenda.json gordea: %d ekitaldi", len(ekitaldiak_ordenatua))


def main():
    logger.info("=== Euskal Agenda eguneraketa hasitzen ===")

    # 1. Dauden ekitaldiak kargatu (aurrekoak)
    dauden_ekitaldiak = kargatu_daudenak()
    logger.info("Dagoeneko gordeak: %d ekitaldi", len(dauden_ekitaldiak))

    # 2. Iturburuetatik datu berriak lortu
    ekitaldiak_gordinak = egin_scraping()
    logger.info("Iturburuetatik jasoak: %d ekitaldi", len(ekitaldiak_gordinak))

    # 3. Normalizatu
    normalizatzailea = Normalizatzailea()
    ekitaldiak_norm = normalizatzailea.normalizatu_guztiak(ekitaldiak_gordinak)

    # 4. ID berriak soilik gehitu (daudenak ez berridatzi)
    berri_kopurua = 0
    for ekitaldia in ekitaldiak_norm:
        eid = ekitaldia.get("id")
        if eid and eid not in dauden_ekitaldiak:
            dauden_ekitaldiak[eid] = ekitaldia
            berri_kopurua += 1
    logger.info("Ekitaldi berri gehituta: %d", berri_kopurua)

    # 5. Zerrenda osoa osatu
    ekitaldi_zerrenda = list(dauden_ekitaldiak.values())

    # 6. Bikoiztunak kendu (ID berdinik ez dagoena, baina izen+data+herri berdina)
    ekitaldi_zerrenda = kendu_bikoiztunak(ekitaldi_zerrenda)

    # 7. Iraganeko ekitaldiak ezabatu
    ekitaldi_zerrenda = iragazki_zaharrak(ekitaldi_zerrenda)

    # 8. Gorde
    gorde_agenda(ekitaldi_zerrenda)
    logger.info("=== Eguneraketa bukatua ===")


if __name__ == "__main__":
    main()
