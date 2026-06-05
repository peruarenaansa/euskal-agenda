# Euskal Agenda

Euskal Herriko euskarazko kultur ekitaldien agenda automatikoa.
Egunero eguneratzen da GitHub Actions bidez eta `data/agenda.json` fitxategian gordetzen.

## Datuak nola kontsumitu

GitHub Pages aktibatuz gero, zuzenean kontsumitu daiteke:
```
https://ZURE-IZENA.github.io/euskal-agenda/data/agenda.json
```
Edo raw GitHub bidez:
```
https://raw.githubusercontent.com/ZURE-IZENA/euskal-agenda/main/data/agenda.json
```

## JSON eskema

```json
{
  "meta": {
    "noiz_eguneratua": "2026-06-05T06:00:00+00:00",
    "ekitaldi_kopurua": 142,
    "iturriak": ["eke.eus", "kulturklik.eus"]
  },
  "ekitaldiak": [
    {
      "id": "a3f8c1d2",
      "ekitaldia": "Haizea taldearen kontzertua",
      "azalpena": "...",
      "mota": "musika",
      "hizkuntza": "eu",
      "hasiera_data": "2026-06-10T19:00:00",
      "bukaera_data": "2026-06-10T21:00:00",
      "lekua": {
        "non": "Kafe Antzokia",
        "herria": "Bilbo",
        "herrialdea": "Bizkaia",
        "koordenatuak": [43.269, -2.934]
      },
      "prezioa": { "zenbatekoa": 12, "moneta": "EUR", "doan": false },
      "url": "https://...",
      "irudiaren_url": "https://...",
      "iturria": "kulturklik.eus",
      "etiketak": [],
      "nabarmendua": "0"
    }
  ]
}
```

## Mota onartuak

| Mota | Azalpena |
|---|---|
| `musika` | Kontzertua, errezitala... |
| `antzerkia` | Antzezlanak |
| `dantza` | Dantza ikuskizunak |
| `ikus-entzunezkoak` | Zinema, audiovisuala |
| `hitzaldiak` | Konferentzia, mahai-inguru, aurkezpen... |
| `bertsolaritza` | Bertso saioak |
| `erakusketak` | Arte erakusketak |
| `haur-jarduera` | Haurrentzako jarduerak |
| `ikastaroak` | Ikastaroak eta tailerrak |
| `bestelakoak` | Gainerako guztiak |

## Instalatzeko (tokian)

```bash
git clone https://github.com/ZURE-IZENA/euskal-agenda.git
cd euskal-agenda
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Cron-aren logika

Egunero exekutatzean:
- Iturburuetatik ekitaldi **berriak** soilik ekarri (daudenak ez berriz bildu)
- 3 hilabete baino zaharragoak **ezabatu**
- `nabarmendua` eremua **inoiz ez ukitu** (eskuz ezarri daiteke)

## Iturri berriak gehitu

1. `scrapers/` karpetan klase berri bat sortu `BaseScraper` heredatuz
2. `config/iturriak.yml`-n sarrera berri bat gehitu
3. `main.py`-ko `egin_scraping()` funtzioan instantziatu

## Lizentzia

MIT
