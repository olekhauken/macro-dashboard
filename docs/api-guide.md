# API-guide – yfinance

> Praktisk guide til yfinance-biblioteket: hva det kan, hvordan vi bruker det,
> og fallgruver du bør kjenne til.

---

## Hva er yfinance?

`yfinance` er en Python-wrapper rundt Yahoo Finance sitt web-API.
Det er *ikke* et offisielt API – yfinance skraper/kaller Yahoo Finance
sine interne endepunkter. Det er gratis og krever ingen API-nøkkel.

**Installasjon:**
```bash
pip install yfinance
```

---

## Hente data for én ticker

```python
import yfinance as yf

# Last ned 1 år med daglige sluttpriser for S&P 500
ticker = yf.Ticker("^GSPC")
df = ticker.history(period="1y", interval="1d")

print(df.head())
# Output: DataFrame med kolonner Open, High, Low, Close, Volume, Dividends, Stock Splits
# Index: Dato (pandas DatetimeIndex)
```

### Viktig: `auto_adjust`
Når du bruker `.history()` er `auto_adjust=True` som standard.
Dette justerer prisene for aksjesplitter og utbytte automatisk.
Vi bruker `auto_adjust=True` konsekvent i dette prosjektet.

---

## Batch-download (vår metode)

For å laste ned mange tickers effektivt bruker vi `yf.download()`:

```python
import yfinance as yf

symbols = ["^OSEBX", "^GSPC", "^IXIC", "^VIX"]

df = yf.download(
    tickers=" ".join(symbols),  # Mellomromseparert streng
    period="1y",                # Siste 1 år
    interval="1d",              # Daglige data
    group_by="ticker",          # Gruppert per ticker i kolonne-indeksen
    auto_adjust=True,           # Justert for splitter/utbytte
    progress=False,             # Skjul nedlastingsbar
    threads=True,               # Parallell nedlasting
)

# Hent sluttpriser for OSEBX:
osebx_close = df["Close"]["^OSEBX"]
```

### Strukturen på DataFrame fra batch-download

Med `group_by="ticker"` får du et hierarkisk kolonneindeks:

```
          ^OSEBX                    ^GSPC
          Close  High  Low  Open   Close  High  Low  Open
Date
2024-01-02  ...   ...  ...  ...     ...   ...  ...  ...
2024-01-03  ...   ...  ...  ...     ...   ...  ...  ...
```

Du navigerer til en ticker slik:
```python
df["Close"]["^GSPC"]          # S&P 500 sluttpriser
df[("Close", "^GSPC")]        # Identisk, alternativ syntaks
```

---

## Tilgjengelige perioder

| Kode  | Betydning          |
|-------|--------------------|
| `1d`  | Siste dag          |
| `5d`  | Siste 5 dager      |
| `1mo` | Siste måned        |
| `3mo` | Siste 3 måneder    |
| `6mo` | Siste 6 måneder    |
| `1y`  | Siste år (vi bruker dette) |
| `2y`  | Siste 2 år         |
| `5y`  | Siste 5 år         |
| `10y` | Siste 10 år        |
| `ytd` | Fra årets start    |
| `max` | All tilgjengelig historikk |

---

## Tilgjengelige intervaller

| Kode   | Tilgjengelig for         |
|--------|--------------------------|
| `1m`   | Siste 7 dager            |
| `5m`   | Siste 60 dager           |
| `15m`  | Siste 60 dager           |
| `1h`   | Siste 730 dager          |
| `1d`   | Full historikk (vi bruker dette) |
| `1wk`  | Full historikk           |
| `1mo`  | Full historikk           |

---

## Fallgruver og kjente problemer

### 1. Oslo Børs-tickers kan mangle data
`^OSEBX` og `^OBX` er ikke alltid tilgjengelige via Yahoo Finance,
spesielt utenfor norsk børsåpningstid (09:00–16:30 CET).

**Løsning:** Sjekk at serien ikke er tom, og logg et `WARNING` i stedet for
å kaste en exception – dashboard-en kan vise "Data ikke tilgjengelig"
uten å krasje.

```python
close = df["Close"]["^OSEBX"].dropna()
if len(close) < 2:
    logging.warning("Ikke nok data for ^OSEBX")
    return None
```

### 2. Rate-limiting ved mange kall
Yahoo Finance begrenser antall kall per minutt (udokumentert grense).

**Løsning:** Bruk batch-download i stedet for én request per ticker.
Én `yf.download()` med alle symboler er mye mer effektivt enn 11 separate kall.

### 3. `Empty DataFrame` på ukjente symboler
Hvis et ticker-symbol er feil (f.eks. `^WRONGSYMBOL`) returnerer yfinance
et tomt DataFrame uten feilmelding.

**Løsning:** Sjekk alltid `if raw.empty:` etter download.

### 4. Tidssoner og NaN på ikke-handelsdager
`yf.download()` returnerer NaN for dager markedet er stengt (helligdager).
Bruk `dropna()` på `Close`-kolonnen for å fjerne disse radene.

```python
close = df["Close"]["^GSPC"].dropna()
```

### 5. API-endringer (ustabilitet)
Siden yfinance ikke er et offisielt API kan Yahoo endre strukturen uten varsel.
Pinne yfinance-versjonen i `requirements.txt` beskytter mot uventede endringer:

```
yfinance==0.2.51
```

---

## Eksempel: Hente og inspisere metadata

```python
ticker = yf.Ticker("^GSPC")

# Generell info
info = ticker.info
print(info["longName"])     # "S&P 500"
print(info["currency"])     # "USD"

# Siste kurs
print(info["regularMarketPrice"])     # Nåværende pris
print(info["regularMarketChange"])    # Endring i dag
print(info["regularMarketChangePercent"])  # Prosent endring
```

> **Merk:** `ticker.info` gjør en ekstra HTTP-request. Bruk det for
> metadata, ikke for historiske tidsserier.

---

## Relevante lenker

- [yfinance GitHub](https://github.com/ranaroussi/yfinance)
- [yfinance PyPI](https://pypi.org/project/yfinance/)
- [Yahoo Finance ticker-søk](https://finance.yahoo.com/lookup/)
