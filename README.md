# macro-dashboard

Et personlig, interaktivt makroøkonomisk dashboard bygget med Python og Dash.

Viser børsindekser, volatilitet og råvarepriser med historiske tidsserier,
KPI-kort og interaktive grafer.

---

## Hva prosjektet er

`macro-dashboard` henter daglige EOD-data (End of Day) fra Yahoo Finance og
presenterer dem i et nettbasert dashboard. Dashboardet oppdateres automatisk
én gang per dag via en innebygd scheduler.

**Nåværende datakilder:**
- Oslo Børs: OSEBX, OBX
- Globale indekser: S&P 500, NASDAQ, Dow Jones, DAX, FTSE 100, Nikkei 225, Shanghai
- Volatilitet: VIX
- Råvarer: Brent crude oil

---

## Kjør lokalt

### Forutsetninger
- Python 3.11+
- pip

### Installasjon

```bash
# Klon repoet
git clone https://github.com/DITT-BRUKERNAVN/macro-dashboard.git
cd macro-dashboard

# Opprett virtuelt miljø
python -m venv venv

# Aktiver (macOS/Linux)
source venv/bin/activate

# Aktiver (Windows)
venv\Scripts\activate

# Installer avhengigheter
pip install -r requirements.txt
```

### Hent data (første gang)

```bash
python -m data.fetchers.fetch_market
```

Dette laster ned de siste 12 månedene med data og lagrer til `data/store/market.json`.

### Verifiser at data er hentet korrekt

```bash
python test_market.py
```

Du skal se en tabell med alle tickers, siste kurs og daglig endring.

### Start dashboardet

```bash
python app.py
```

Åpne nettleser og gå til [http://localhost:8050](http://localhost:8050).

---

## Prosjektstruktur

```
macro-dashboard/
├── app.py                  # Dash-appen
├── scheduler.py            # Daglig datahenting
├── data/
│   ├── fetchers/
│   │   ├── base.py         # Abstrakt baseklasse
│   │   └── fetch_market.py # Børsdata via yfinance
│   └── store/              # Lagrede JSON-filer
├── docs/                   # Dokumentasjon
├── requirements.txt
├── Procfile                # Railway
└── README.md
```

Se `docs/architecture.md` for en fullstendig gjennomgang av stackvalg og dataflyt.

---

## Deploy til Railway

### Forutsetninger
- Konto på [railway.app](https://railway.app)
- Railway CLI installert: `npm install -g @railway/cli`

### Steg

```bash
# Logg inn
railway login

# Initialiser prosjekt (kjøres én gang)
railway init

# Deploy
railway up
```

Railway leser `Procfile` og starter appen med gunicorn automatisk.

### Miljøvariabler

Ingen API-nøkler er nødvendig for yfinance. Sett disse i Railway-dashboardet
hvis du legger til andre datakilder:

| Variabel          | Beskrivelse                   |
|-------------------|-------------------------------|
| `PORT`            | Settes automatisk av Railway  |

---

## Legge til ny datakilde

Se `docs/howto-add-datasource.md` for en steg-for-steg guide.

---

## Teknologier

| Bibliotek    | Versjon  | Brukes til                    |
|--------------|----------|-------------------------------|
| Dash         | 2.18     | Dashboard-framework           |
| Plotly       | 5.24     | Interaktive grafer            |
| yfinance     | 0.2.51   | Børs- og indeksdata           |
| pandas       | 2.2      | Databehandling                |
| APScheduler  | 3.10     | Daglig datahenting            |
| gunicorn     | 23.0     | Produksjons-webserver         |
