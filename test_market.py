"""
test_market.py
==============
Quick smoke-test script for the MarketFetcher.

This is *not* a full test suite (no pytest) – it's a learning-friendly
script that prints clear output so you can visually verify that:

  1. The fetcher returns data in the correct contract format
  2. All expected tickers are present
  3. Each series has the expected fields
  4. Change calculations look reasonable (last entry vs second-to-last)

Run with:
    python test_market.py

Expected output:
    - A list of all tickers with their latest price and 1-day change
    - A section showing the first and last series entry for OSEBX
    - A PASS/FAIL summary for each contract-validation check
"""

import json
import sys
import logging
from pathlib import Path

# Add project root to sys.path so imports work when running from root.
# (Not needed when running as a module, but handy for direct script execution.)
sys.path.insert(0, str(Path(__file__).parent))

from data.fetchers.fetch_market import MarketFetcher, ALL_TICKERS
from data.fetchers.base import BaseFetcher

# Show INFO logs so we can see what yfinance is doing under the hood.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

print("=" * 65)
print("  macro-dashboard  |  Market Fetcher Smoke Test")
print("=" * 65)

# ---------------------------------------------------------------------------
# Step 1: Fetch live data
# ---------------------------------------------------------------------------
print("\n[1/4] Fetching data from Yahoo Finance...")
fetcher = MarketFetcher()
data = fetcher.fetch()

if not data:
    print("\n❌  FATAL: fetch() returned empty list. Check network / yfinance.")
    sys.exit(1)

print(f"      → Got {len(data)} tickers (expected {len(ALL_TICKERS)})")

# ---------------------------------------------------------------------------
# Step 2: Validate contract format for every ticker
# ---------------------------------------------------------------------------
print("\n[2/4] Validating contract format...")
all_valid = True
for entry in data:
    ok = BaseFetcher.validate(entry)
    status = "✓" if ok else "✗"
    if not ok:
        all_valid = False
    # Also check that each series entry has the required fields
    for point in entry["series"]:
        for field in ("date", "value", "change_abs", "change_pct"):
            if field not in point:
                print(f"  ✗  {entry['label']}: series entry missing field '{field}'")
                all_valid = False
                break
    print(f"  {status}  {entry['label']} ({entry['ticker']})")

if all_valid:
    print("\n  ✓ All tickers passed contract validation.")
else:
    print("\n  ✗ Some tickers failed contract validation – see above.")

# ---------------------------------------------------------------------------
# Step 3: Print latest price snapshot (the "KPI card" data)
# ---------------------------------------------------------------------------
print("\n[3/4] Latest prices and 1-day changes:\n")
print(f"  {'Ticker':<12}  {'Label':<35}  {'Price':>12}  {'Change':>10}  {'Change %':>10}")
print("  " + "-" * 85)

for entry in data:
    last = entry["series"][-1]
    sign = "+" if last["change_pct"] >= 0 else ""
    arrow = "▲" if last["change_pct"] >= 0 else "▼"
    print(
        f"  {entry['ticker']:<12}  "
        f"{entry['label']:<35}  "
        f"{last['value']:>12,.2f}  "
        f"{sign}{last['change_abs']:>9,.2f}  "
        f"{arrow} {sign}{last['change_pct']:>7.2f}%"
    )

# ---------------------------------------------------------------------------
# Step 4: Deep-dive on OSEBX – show first and last series entries
# ---------------------------------------------------------------------------
print("\n[4/4] Deep-dive: OSEBX series (first 3 and last 3 entries)\n")
osebx = next((e for e in data if e["ticker"] == "^OSEBX"), None)

if osebx is None:
    print("  ⚠  OSEBX not found in results (might not be available today).")
else:
    print(f"  Ticker        : {osebx['ticker']}")
    print(f"  Label         : {osebx['label']}")
    print(f"  Granularity   : {osebx['granularity']}")
    print(f"  Last updated  : {osebx['last_updated']}")
    print(f"  Series length : {len(osebx['series'])} days\n")

    sample_entries = osebx["series"][:3] + ["..."] + osebx["series"][-3:]
    for entry in sample_entries:
        if entry == "...":
            print("  ...")
            continue
        sign = "+" if entry["change_pct"] >= 0 else ""
        print(
            f"  {entry['date']}  "
            f"value={entry['value']:>10,.2f}  "
            f"abs={sign}{entry['change_abs']:>8,.2f}  "
            f"pct={sign}{entry['change_pct']:>6.2f}%"
        )

# ---------------------------------------------------------------------------
# Step 5: Save to disk and verify the file
# ---------------------------------------------------------------------------
print("\n[5/5] Saving to data/store/market.json...")
fetcher.save(data)

saved_path = Path("data/store/market.json")
if saved_path.exists():
    size_kb = saved_path.stat().st_size / 1024
    print(f"  ✓  File written: {saved_path}  ({size_kb:.1f} KB)")

    # Re-read and spot-check so we know the file is valid JSON
    with open(saved_path, encoding="utf-8") as f:
        reloaded = json.load(f)
    print(f"  ✓  Re-loaded {len(reloaded)} entries from disk – JSON is valid.")
else:
    print("  ✗  File not found after save – check write permissions.")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 65)
expected = len(ALL_TICKERS)
actual = len(data)
if actual == expected and all_valid:
    print(f"  ALL CHECKS PASSED  ({actual}/{expected} tickers, contract valid)")
elif actual < expected:
    missing = expected - actual
    print(f"  PARTIAL SUCCESS  ({actual}/{expected} tickers – {missing} missing)")
    print("  This is often normal: OSEBX/OBX may not be available via")
    print("  Yahoo Finance outside Norwegian market hours.")
else:
    print(f"  CHECKS FAILED  – see output above for details")
print("=" * 65 + "\n")
