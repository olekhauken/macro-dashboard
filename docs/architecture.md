# Architecture – macro-dashboard

> En forklaring av stackvalg, prosjektstruktur og hvordan delene henger sammen.
> Målgruppen er deg selv om 3 måneder – eller en ny bidragsyter som ikke kjenner koden.

---

## Hva er dette prosjektet?

`macro-dashboard` er et personlig, interaktivt dashboard for makroøkonomiske data.
Det viser børsindekser, renter, råvarepriser og andre indikatorer i sanntid (EOD)
med historiske tidsserier og nøkkeltall (KPI-kort).

---

## Stackvalg

### Python
Standardvalg for data-prosjekter. Bredt biblioteksøkosystem, spesielt for
finansdata (pandas, yfinance) og visualisering (Plotly/Dash).

### Dash (Plotly)
Dash lar oss skrive hele appen – frontend og backend – i Python.
Vi trenger ikke skrive HTML, CSS eller JavaScript.

Alternativet var Streamlit (enklere å starte med) eller en ren Flask + React-stack
(mer fleksibel, men mye mer kode). Dash er midt i mellom: god nok for avanserte
interaktive grafer uten å kreve frontend-kunnskap.

Under panseret er Dash en Flask-applikasjon med React-komponenter. Det betyr at
`gunicorn` kan serve appen direkte – ingen ekstra webserver nødvendig.

### yfinance
Open-source Python-wrapper rundt Yahoo Finance sitt (udokumenterte) API.
Gratis, ingen API-nøkkel, god dekning av globale indekser og aksjer.

**Kjente begrensninger:**
- Ikke offisielt støttet (Yahoo kan endre APIet uten varsel)
- Oslo Børs-data (`^OSEBX`, `^OBX`) kan mangle utenfor norsk åpningstid
- Rate-limiting kan inntreffe ved mange kall – bruk batch-download

### APScheduler
Enkelt Python-bibliotek for å kjøre jobber på faste tidspunkter.
Vi bruker det til å hente ny data én gang per dag etter børsstengetid.

Alternativ: Celery + Redis (mye tyngre), cron på serveren (ikke portabelt),
Railway Cron Jobs (funker, men binder oss til plattformen).

### Railway
PaaS-plattform som deployer direkte fra GitHub. Vi trenger bare å pushe kode,
så bygger og starter Railway appen automatisk via `Procfile`.

---

## Prosjektstruktur

```
macro-dashboard/
├── app.py                  # Dash-appen: layout, callbacks, server
├── scheduler.py            # APScheduler: daglig datahenting
│
├── data/
│   ├── fetchers/
│   │   ├── __init__.py     # Eksporterer BaseFetcher
│   │   ├── base.py         # Abstrakt baseklasse – datakilde-kontrakten
│   │   └── fetch_market.py # Børsdata via yfinance
│   └── store/
│       └── market.json     # Siste hentede data (skrives av fetchers)
│
├── docs/                   # Dokumentasjon (denne mappen)
│
├── requirements.txt        # Python-avhengigheter
├── Procfile                # Railway-konfigurasjon
└── README.md
```

---

## Dataflyt

```
                     ┌─────────────────────────────────┐
                     │          scheduler.py            │
                     │  (kjører daglig etter børsslutt) │
                     └────────────────┬────────────────┘
                                      │ kaller fetch()
                                      ▼
                     ┌─────────────────────────────────┐
                     │        MarketFetcher             │
                     │   (data/fetchers/fetch_market)   │
                     │                                  │
                     │  yf.download() → rå DataFrame    │
                     │  → transformerer til kontrakt    │
                     │  → lagrer til data/store/        │
                     └────────────────┬────────────────┘
                                      │ skriver JSON
                                      ▼
                     ┌─────────────────────────────────┐
                     │     data/store/market.json       │
                     │   (én fil per datakilde)         │
                     └────────────────┬────────────────┘
                                      │ leses av
                                      ▼
                     ┌─────────────────────────────────┐
                     │            app.py                │
                     │   Dash-layout + callbacks        │
                     │   leser JSON → viser i nettleser │
                     └─────────────────────────────────┘
```

---

## Datakilde-kontrakten

Alle fetchers returnerer data i ett standardisert format (definert i `base.py`):

```python
{
    "source":       str,          # f.eks. "yfinance", "ssb", "fred"
    "label":        str,          # f.eks. "Oslo Børs – OSEBX"
    "ticker":       str,          # (valgfri) f.eks. "^OSEBX"
    "granularity":  str,          # "daily" | "weekly" | "monthly" | "quarterly"
    "last_updated": str,          # ISO-8601, f.eks. "2024-01-15T14:30:00+00:00"
    "series": [
        {
            "date":       "YYYY-MM-DD",
            "value":      float,
            "change_abs": float,  # absolutt endring vs forrige periode
            "change_pct": float   # prosentvis endring vs forrige periode
        }
    ]
}
```

Fordelen med dette mønsteret: `app.py` trenger ikke å vite om data kommer
fra yfinance, SSB eller en annen kilde – det leser alltid samme format.

---

## Utvidelsespunkter

| Hva du vil legge til     | Fil å lage / endre                        |
|--------------------------|-------------------------------------------|
| Ny datakilde             | `data/fetchers/fetch_XXX.py` + scheduler  |
| Ny visualisering         | Ny callback i `app.py`                    |
| Ny side / fane           | Nytt `dcc.Tab` i layout i `app.py`        |
| Ny deployment-plattform  | Oppdater `Procfile` og env-variabler      |

Se `docs/howto-add-datasource.md` for steg-for-steg guide.
