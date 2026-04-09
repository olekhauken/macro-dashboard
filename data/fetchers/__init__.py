# data/fetchers/__init__.py
#
# This package contains all data-source modules for the macro dashboard.
# Each module must implement the BaseFetcher interface defined in base.py.
#
# Current fetchers:
#   - fetch_market.py  →  Stock indices and commodities via yfinance
#
# To add a new data source, see docs/howto-add-datasource.md.

from data.fetchers.base import BaseFetcher

__all__ = ["BaseFetcher"]
