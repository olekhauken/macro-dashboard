"""
data/fetchers/base.py
=====================
Defines the abstract base class (contract) that every data-source fetcher
must implement.

Why a base class?
-----------------
A shared interface ("contract") means the dashboard never needs to know
*where* data comes from – it just calls `fetcher.fetch()` and gets back
data in a predictable shape. Adding a new source (e.g. SSB, FRED, ECB)
only requires writing a new class that inherits from BaseFetcher.

This pattern is called the "Template Method" / "Strategy" pattern and is
a standard way to decouple data-collection from data-presentation.

Output contract (the dict every fetcher must return)
-----------------------------------------------------
{
    "source":       str,          # Machine-readable ID, e.g. "yfinance"
    "label":        str,          # Human-readable name, e.g. "Oslo Børs – OSEBX"
    "granularity":  str,          # One of: "daily", "weekly", "monthly", "quarterly"
    "last_updated": str,          # ISO-8601 UTC timestamp, e.g. "2024-01-15T14:30:00Z"
    "series": [
        {
            "date":       str,    # "YYYY-MM-DD"
            "value":      float,  # Closing price / index level / rate
            "change_abs": float,  # Absolute change vs previous period
            "change_pct": float   # Percentage change vs previous period (e.g. -1.23 = -1.23 %)
        },
        ...
    ]
}
"""

from abc import ABC, abstractmethod
from typing import Literal


# The allowed granularity values – we use a Literal type so static analysis
# tools (mypy, Pylance) can catch typos at development time.
Granularity = Literal["daily", "weekly", "monthly", "quarterly"]


class BaseFetcher(ABC):
    """
    Abstract base class for all macro-dashboard data fetchers.

    Subclass this and implement `fetch()` to plug in a new data source.
    The returned dict must conform to the output contract above.

    Example
    -------
    >>> class MyFetcher(BaseFetcher):
    ...     def fetch(self) -> dict:
    ...         return {
    ...             "source": "my_api",
    ...             "label": "My Indicator",
    ...             "granularity": "monthly",
    ...             "last_updated": "2024-01-15T12:00:00Z",
    ...             "series": [{"date": "2024-01-01", "value": 100.0,
    ...                         "change_abs": 1.5, "change_pct": 1.52}]
    ...         }
    """

    @abstractmethod
    def fetch(self) -> dict:
        """
        Fetch data from the source and return it in the standard contract format.

        Returns
        -------
        dict
            A dictionary matching the output contract documented at the top of
            this file. All fields are required.

        Raises
        ------
        NotImplementedError
            If the subclass does not implement this method (enforced by ABC).
        Exception
            Subclasses may raise source-specific exceptions (network errors,
            parsing errors, etc.). Callers should handle these gracefully.
        """
        raise NotImplementedError

    @staticmethod
    def validate(data: dict) -> bool:
        """
        Validate that a data dict conforms to the output contract.

        This is a lightweight sanity-check used in tests and during development.
        It does *not* validate individual series entries – just the top-level keys.

        Parameters
        ----------
        data : dict
            The dict returned by a fetcher's `fetch()` method.

        Returns
        -------
        bool
            True if the dict has all required top-level keys, False otherwise.
        """
        required_keys = {"source", "label", "granularity", "last_updated", "series"}
        missing = required_keys - data.keys()
        if missing:
            # Print which keys are missing so tests give useful error messages.
            print(f"[BaseFetcher.validate] Missing keys: {missing}")
            return False

        # Verify granularity is one of the allowed values
        allowed_granularities = {"daily", "weekly", "monthly", "quarterly"}
        if data["granularity"] not in allowed_granularities:
            print(f"[BaseFetcher.validate] Invalid granularity: {data['granularity']!r}")
            return False

        # Verify series is a non-empty list
        if not isinstance(data["series"], list) or len(data["series"]) == 0:
            print("[BaseFetcher.validate] 'series' must be a non-empty list")
            return False

        return True
