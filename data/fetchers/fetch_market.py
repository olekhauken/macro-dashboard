"""
data/fetchers/fetch_market.py
=============================
Fetches end-of-day (EOD) price data for stock market indices and commodities
using the yfinance library (Yahoo Finance).

Implements the BaseFetcher contract, so the dashboard can consume this data
the same way as any future data source (SSB, FRED, ECB, etc.).

Data saved to: data/store/market.json

Tickers covered
---------------
Oslo Børs:
  ^OSEBX   – Oslo Børs Benchmark Index (hovedindeks)
  ^OBX     – Oslo Børs 25 most liquid stocks

Global indices:
  ^GSPC    – S&P 500
  ^IXIC    – NASDAQ Composite
  ^DJI     – Dow Jones Industrial Average
  ^GDAXI   – DAX (Germany)
  ^FTSE    – FTSE 100 (UK)
  ^N225    – Nikkei 225 (Japan)
  000001.SS – Shanghai Composite (China)

Volatility & commodities:
  ^VIX     – CBOE Volatility Index ("fear gauge")
  BZ=F     – Brent Crude Oil futures (USD/barrel)

Usage
-----
Run directly to fetch and print a summary:

    python -m data.fetchers.fetch_market

Or import and use in other modules:

    from data.fetchers.fetch_market import MarketFetcher
    fetcher = MarketFetcher()
    data = fetcher.fetch()          # Returns list of contract dicts
    fetcher.save(data)              # Writes to data/store/market.json
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from data.fetchers.base import BaseFetcher

# ---------------------------------------------------------------------------
# Logging setup
# Using the module's own logger (not the root logger) is best practice – it
# lets callers control verbosity without touching global logging config.
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ticker definitions
# Grouped by category so it's easy to add/remove individual symbols.
# Each entry: (ticker_symbol, human_readable_label)
# ---------------------------------------------------------------------------
OSLO_BORS_TICKERS = [
    # ^OSEBX og ^OBX (med ^) finnes ikke i Yahoo Finance.
    # OBX.OL er Oslo Børs OBX-indeksen direkte på Yahoo Finance (uten ^).
    # EQNR.OL er Equinor – Norges største selskap og tung vekt i OBX.
    ("OBX.OL",   "Oslo Børs – OBX 25"),
    ("EQNR.OL",  "Equinor (EQNR)"),
]

GLOBAL_INDEX_TICKERS = [
    ("^GSPC",    "S&P 500"),
    ("^IXIC",    "NASDAQ Composite"),
    ("^DJI",     "Dow Jones"),
    ("^GDAXI",   "DAX"),
    ("^FTSE",    "FTSE 100"),
    ("^N225",    "Nikkei 225"),
    ("000001.SS","Shanghai Composite"),
]

OTHER_TICKERS = [
    ("^VIX", "VIX – Volatility Index"),
    ("BZ=F", "Brent Crude Oil (USD/bbl)"),
]

# Oslo Børs comes first in the final list – that is intentional.
# The dashboard renders tickers in this order, so Norwegian indices are
# always displayed at the top.
ALL_TICKERS = OSLO_BORS_TICKERS + GLOBAL_INDEX_TICKERS + OTHER_TICKERS

# How far back we fetch history (used for the time-series chart).
HISTORY_PERIOD = "1y"

# Where to save the output file (relative to project root).
STORE_PATH = Path("data/store/market.json")


class MarketFetcher(BaseFetcher):
    """
    Fetches end-of-day price data for all configured market tickers.

    Inherits from BaseFetcher, which enforces the output contract.
    Each ticker becomes one entry in the list returned by `fetch()`.

    Why one object per ticker, not one big dataframe?
    -------------------------------------------------
    Keeping each ticker as its own contract dict makes it trivial to:
    - Add a ticker without touching any other code
    - Cache or update individual tickers independently
    - Display per-ticker metadata (label, last_updated) in the UI
    """

    def fetch(self) -> list[dict]:
        """
        Fetch 1-year daily EOD data for all tickers in ALL_TICKERS.

        Uses yfinance's batch download for efficiency (one HTTP request per
        group of tickers, not one per ticker).

        Returns
        -------
        list[dict]
            A list where each element is a contract dict (see base.py).
            Returns an empty list if the download fails entirely.
        """
        logger.info("Fetching market data for %d tickers...", len(ALL_TICKERS))

        # yfinance batch download: pass all symbols as a space-separated string.
        # group_by="ticker" puts each symbol in its own column group in the result.
        # auto_adjust=True adjusts prices for splits and dividends automatically,
        # so we always work with "clean" closing prices.
        symbols = [t[0] for t in ALL_TICKERS]
        raw = yf.download(
            tickers=" ".join(symbols),
            period=HISTORY_PERIOD,
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,   # Suppress the download progress bar
            threads=True,     # Parallel downloads per ticker
        )

        if raw.empty:
            logger.error("yfinance returned an empty DataFrame – check your network connection.")
            return []

        results = []
        for symbol, label in ALL_TICKERS:
            try:
                series_data = self._extract_series(raw, symbol, len(symbols))
                if series_data is None:
                    continue

                contract = {
                    "source": "yfinance",
                    "label": label,
                    "ticker": symbol,       # Extra field – useful for the dashboard
                    "granularity": "daily",
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "series": series_data,
                }
                results.append(contract)
                logger.debug("  ✓ %s (%s): %d data points", label, symbol, len(series_data))

            except Exception as exc:
                # Log and skip this ticker – don't let one bad ticker crash the whole fetch.
                logger.warning("  ✗ Failed to process %s (%s): %s", label, symbol, exc)

        logger.info("Successfully fetched data for %d/%d tickers.", len(results), len(ALL_TICKERS))
        return results

    def _extract_series(self, raw: pd.DataFrame, symbol: str, num_symbols: int) -> list[dict] | None:
        """
        Extract and transform price data for a single ticker from the raw
        yfinance DataFrame into the contract's 'series' format.

        Parameters
        ----------
        raw : pd.DataFrame
            The full DataFrame returned by yf.download() for all tickers.
        symbol : str
            The Yahoo Finance ticker symbol to extract (e.g. "^OSEBX").
        num_symbols : int
            Total number of symbols downloaded. When only 1 symbol is
            requested, yfinance returns a flat DataFrame (no ticker-level
            MultiIndex), so we need to handle that case separately.

        Returns
        -------
        list[dict] or None
            List of series dicts, or None if data for this symbol is missing
            or has too few rows to compute changes.
        """
        # ---- Select the "Close" column for this ticker ----
        # yfinance 1.x changed the MultiIndex column order:
        #   Old (<=0.2.x): (field, ticker)  → raw["Close"]["^GSPC"]
        #   New (>=1.0.0): (ticker, field)  → raw["^GSPC"]["Close"]
        # When only one ticker is downloaded the column index is flat: just the field.
        if num_symbols == 1:
            # Single-ticker download: flat column index
            close = raw["Close"]
        elif raw.columns.nlevels == 2:
            # Multi-ticker download: detect column order by checking level 0 values.
            # If level 0 contains ticker symbols (e.g. "^GSPC"), it's the new 1.x format.
            level0_values = raw.columns.get_level_values(0).unique().tolist()
            new_format = any(v in level0_values for v in ["^GSPC", "^IXIC", "^VIX", symbol])
            if new_format:
                # yfinance 1.x: (ticker, field)
                if symbol not in raw.columns.get_level_values(0):
                    logger.warning("Symbol %s not found in downloaded data.", symbol)
                    return None
                close = raw[symbol]["Close"]
            else:
                # yfinance 0.x: (field, ticker)
                if symbol not in raw.columns.get_level_values(1):
                    logger.warning("Symbol %s not found in downloaded data.", symbol)
                    return None
                close = raw["Close"][symbol]
        else:
            logger.warning("Unexpected DataFrame structure for %s.", symbol)
            return None

        # Drop any rows where the close price is NaN (market holidays, weekends).
        close = close.dropna()

        if len(close) < 2:
            logger.warning("Not enough data points for %s (got %d).", symbol, len(close))
            return None

        # ---- Compute period-over-period changes ----
        # diff() gives absolute change vs the previous row.
        # pct_change() gives the fractional change; multiplied by 100 → percentage.
        abs_changes = close.diff()
        pct_changes = close.pct_change() * 100

        series = []
        for date, value in close.items():
            # date is a pandas Timestamp; convert to plain "YYYY-MM-DD" string.
            date_str = date.strftime("%Y-%m-%d")

            change_abs = abs_changes[date]
            change_pct = pct_changes[date]

            # NaN on the first row (no previous period) – default to 0.0
            # rather than propagating NaN into our JSON output.
            series.append({
                "date":       date_str,
                "value":      round(float(value), 4),
                "change_abs": round(float(change_abs) if pd.notna(change_abs) else 0.0, 4),
                "change_pct": round(float(change_pct) if pd.notna(change_pct) else 0.0, 4),
            })

        return series

    def save(self, data: list[dict], path: Path = STORE_PATH) -> None:
        """
        Persist fetched data to a JSON file on disk.

        The file is overwritten on each run – this is intentional, as the
        scheduler fetches fresh data daily and the file always reflects the
        latest snapshot.

        Parameters
        ----------
        data : list[dict]
            The list of contract dicts returned by `fetch()`.
        path : Path
            Destination file path. Defaults to data/store/market.json.
        """
        # Ensure the directory exists (creates data/store/ if needed).
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            # indent=2 keeps the file human-readable for debugging.
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("Saved %d tickers to %s", len(data), path)


# ---------------------------------------------------------------------------
# Module entry point – allows running directly: python -m data.fetchers.fetch_market
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    fetcher = MarketFetcher()
    data = fetcher.fetch()

    if data:
        fetcher.save(data)
        print(f"\nFetched {len(data)} tickers. Snapshot of last data points:\n")
        for entry in data:
            last = entry["series"][-1]
            sign = "+" if last["change_pct"] >= 0 else ""
            print(
                f"  {entry['label']:<35}  "
                f"{last['value']:>10,.2f}   "
                f"{sign}{last['change_pct']:.2f}%"
            )
    else:
        print("No data fetched. Check logs for details.")
