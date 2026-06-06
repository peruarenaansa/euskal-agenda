"""
main.py — Euskal Agenda, sarrera-puntu nagusia.

Cron-aren logika:
  - agenda.json badago: dauden ekitaldiak MANTENDU
  - Iturburuetatik BERRI direnak soilik gehitu (dauden ID-ak ez berriro)
  - (Cancelado) / (Suspendido) dutenak EZABATU (berriak eta dauden zaharrak biak)
  - Gaztelaniazko eta frantsesezko ekitaldiak BAZTERTU
  - 3 hilabete baino zaharragoak EZABATU
"""
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from scrapers.kulturklik import KulturklikScraper
from scrapers.eke import EkeScraper
from processors.normalizer import Normalizatzailea
from processors.deduplicator import kendu_bikoiztunak
from processors.hizkuntza import hizkuntza_iragaztu

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

DATA_DIR = Path(__file__).parent / "data"
AGENDA_FITXATEGIA = DATA_DIR / "agenda.json"
IRAGANEKO_HILABETEAK = 3

# Ekitaldia bertan behera edo etetea adierazten duten patroiak
BAZTERTU_PATROIAK = re.compile(
    r"\((Cancelado|Suspendido|Cancelled|Suspended|Anulado|Atzeratua|Bertan behera)\)",
    re.IGNORECASE,
)


def kargatu_daudenak() -> dict[str, dict]:
    if not AGENDA_FITXATEGIA.exists():
        return {}
    try:
        agenda = json.loads(AGENDA_FITXATEGIA.read_text(encoding="utf-8"))
        ekitaldiak = agenda.get("ekitaldiak", [])
        return {e["id"]: e for e in ekitaldiak if e.get("id")}
    except Exception as e:
        logger.warning("agenda.json kargatzean errorea: %s", e)
        return {}


def iragazki_bertan_behera(ekitaldiak: list[dict]) -> list[dict]:
    """Cancelado / Suspendido patroiak dituzten ekitaldiak ezabatu."""
    garbiak = [
        e for e in ekitaldiak
        if not BAZTERTU_PATROIAK.search(e.get("ekitaldia", ""))
    ]
    kendu = len(ekitaldiak) - len(garbiak)
    if kendu:
        logger.info("Bertan behera / suspenditu ekitaldiak ezabatuta: %d", kendu)
    return garbiak


def iragazki_zaharrak(ekitaldiak: list[dict]) -> list[dict]:
    muga = datetime.now() - timedelta(days=30 * IRAGANEKO_HILABETEAK)
    muga_str = muga.strftime("%Y-%m-%d")
    garbiak = [
        e for e in ekitaldiak
        if not e.get("hasiera_data") or e["hasiera_data"][:10] >= muga_str
    ]
    kendu = len(ekitaldiak) - len(garbiak)
    if kendu:
        logger.info("Iraganeko ekitaldiak ezabatuta: %d", kendu)
    return garbiak


def egin_scraping() -> list[dict]:
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
    DATA_DIR.mkdir(exist_ok=True)

    def ordenatzeko_gakoa(e):
        data = e.get("hasiera_data") or "9999-12-31"
        ordua = e.get("hasiera_ordua") or "00:00"
        return f"{data}T{ordua}"

    ekitaldiak_ordenatua = sorted(ekitaldiak, key=ordenatzeko_gakoa)
    agenda = {
        "meta": {
            "noiz_eguneratua": datetime.now(timezone.utc).isoformat(),
            "ekitaldi_kopurua": len(ekitaldiak_ordenatua),
            "iturriak": sorted({e.get("iturria", "") for e in ekitaldiak_ordenatua}),
        },
        "ekitaldiak": ekitaldiak_ordenatua,
    }
    AGENDA_FITXATEGIA.write_text(
        json.dumps(agenda, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("agenda.json gordea: %d ekitaldi", len(ekitaldiak_ordenatua))


def main():
    logger.info("=== Euskal Agenda eguneraketa hasitzen ===")

    # 1. Dauden ekitaldiak kargatu
    dauden_ekitaldiak = kargatu_daudenak()
    logger.info("Dagoeneko gordeak: %d", len(dauden_ekitaldiak))

    # 2. Scraping
    ekitaldiak_gordinak = egin_scraping()
    logger.info("Iturburuetatik jasoak: %d", len(ekitaldiak_gordinak))

    # 3. Normalizatu
    normalizatzailea = Normalizatzailea()
    ekitaldiak_norm = normalizatzailea.normalizatu_guztiak(ekitaldiak_gordinak)

    # 4. Hizkuntza iragaztu (euskaraz ez direnak baztertu)
    ekitaldiak_eu = hizkuntza_iragaztu(ekitaldiak_norm)
    logger.info("Hizkuntza iragazketa: %d → %d", len(ekitaldiak_norm), len(ekitaldiak_eu))

    # 5. ID berriak soilik gehitu
    berri_kopurua = 0
    for ekitaldia in ekitaldiak_eu:
        eid = ekitaldia.get("id")
        if eid and eid not in dauden_ekitaldiak:
            dauden_ekitaldiak[eid] = ekitaldia
            berri_kopurua += 1
    logger.info("Ekitaldi berri gehituta: %d", berri_kopurua)

    # 6. Zerrenda osoa
    ekitaldi_zerrenda = list(dauden_ekitaldiak.values())

    # 7. Cancelado / Suspendido ezabatu (dauden zaharrak ere bai)
    ekitaldi_zerrenda = iragazki_bertan_behera(ekitaldi_zerrenda)

    # 8. Bikoiztunak kendu
    ekitaldi_zerrenda = kendu_bikoiztunak(ekitaldi_zerrenda)

    # 9. Iraganekoak ezabatu
    ekitaldi_zerrenda = iragazki_zaharrak(ekitaldi_zerrenda)

    # 10. Gorde
    gorde_agenda(ekitaldi_zerrenda)
    logger.info("=== Eguneraketa bukatua ===")


if __name__ == "__main__":
    main()
