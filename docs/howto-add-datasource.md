# Howto: Legg til en ny datakilde

> Steg-for-steg guide for å koble en ny datakilde til macro-dashboard.
> Eksempelet under viser hvordan du ville lagt til norsk rente-data fra SSB.

---

## Oversikt

Å legge til en ny kilde krever 3–4 endringer:

1. Lag en ny fetcher-klasse i `data/fetchers/`
2. Registrer den i scheduler
3. (Valgfritt) Legg til et nytt visningspanel i `app.py`

Fordi alle fetchers følger samme kontrakt, trenger du **ikke** endre
eksisterende kode – bare legge til nytt.

---

## Steg 1: Opprett `data/fetchers/fetch_XXX.py`

Kopier dette skjelettet og fyll inn din logikk:

```python
"""
data/fetchers/fetch_XXX.py
==========================
Henter [hva datakilden inneholder] fra [kildennavn].

Datakilde: [URL / API-dokumentasjon]
Oppdateres: [Daglig / ukentlig / månedlig]
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from data.fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)

STORE_PATH = Path("data/store/xxx.json")


class XXXFetcher(BaseFetcher):
    """Henter [hva] fra [kilde]."""

    def fetch(self) -> list[dict]:
        """
        Henter data og returnerer en liste med kontrakt-dicts.

        Returns
        -------
        list[dict]
            Hver dict følger BaseFetcher-kontrakten (se base.py).
        """
        # --- Din hente-logikk her ---
        # f.eks.: requests.get(), pandas_datareader, SSB API, osv.

        series = []
        # ... bygg series-listen med {"date", "value", "change_abs", "change_pct"} ...

        result = {
            "source": "xxx",                  # Maskinlesbar ID
            "label": "Min datakilde",         # Menneskelesbar navn
            "granularity": "monthly",         # "daily" | "weekly" | "monthly" | "quarterly"
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "series": series,
        }
        return [result]

    def save(self, data, path=STORE_PATH):
        """Lagrer data til JSON-fil."""
        import json
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Saved to %s", path)
```

---

## Steg 2: Legg til i `scheduler.py`

```python
from data.fetchers.fetch_market import MarketFetcher
from data.fetchers.fetch_xxx import XXXFetcher   # ← ny import

def fetch_all():
    """Kjøres daglig – henter alle datakilder."""
    for FetcherClass, name in [(MarketFetcher, "market"), (XXXFetcher, "xxx")]:
        try:
            fetcher = FetcherClass()
            data = fetcher.fetch()
            fetcher.save(data)
            logging.info("Fetched %s", name)
        except Exception as e:
            logging.error("Failed to fetch %s: %s", name, e)
```

---

## Steg 3: (Valgfritt) Legg til visning i `app.py`

Siden alle datakilder returnerer samme format, er det enkelt å gjenbruke
de samme Dash-komponentene for den nye kilden:

```python
# I app.py, les den nye JSON-filen
import json
from pathlib import Path

def load_xxx():
    path = Path("data/store/xxx.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []
```

Deretter kan du gjenbruke eksisterende KPI-kort og graf-callbacks ved å
sende inn den nye datasettlisten på samme måte som `market.json`.

---

## Sjekkliste

- [ ] `data/fetchers/fetch_XXX.py` opprettet med klasse som arver `BaseFetcher`
- [ ] `fetch()` returnerer riktig kontrakt-format (kjør `BaseFetcher.validate()`)
- [ ] `save()` skriver til `data/store/XXX.json`
- [ ] Lagt til i `scheduler.py`
- [ ] `test_market.py` (eller eget test-script) kjører uten feil
- [ ] Dokumentert i dette dokumentet

---

## Kontrakt-påminnelse

```python
{
    "source":       str,          # "ssb", "fred", "ecb", osv.
    "label":        str,          # Menneskelesbar navn
    "granularity":  str,          # "daily" | "weekly" | "monthly" | "quarterly"
    "last_updated": str,          # ISO-8601 UTC
    "series": [
        {
            "date":       "YYYY-MM-DD",
            "value":      float,
            "change_abs": float,
            "change_pct": float
        }
    ]
}
```
