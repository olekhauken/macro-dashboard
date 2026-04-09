"""
app.py
======
Inngangspunktet for macro-dashboard Dash-appen.

Dette er en placeholder som vi vil utvide i neste steg med:
- KPI-kort per indeks
- Interaktiv graf med tidsserier
- Filtre for dag/uke/måned/kvartal/år
- Dropdown for å velge indekser

Kjøres med:
    python app.py

Eller via gunicorn (Railway):
    gunicorn app:server
"""

import logging
import os

import dash
from dash import html

import scheduler as sched

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dash-app initialisering
# ---------------------------------------------------------------------------
app = dash.Dash(
    __name__,
    title="Macro Dashboard",
    # suppress_callback_exceptions=True gjør at Dash ikke klager over
    # callbacks som refererer til komponenter som ikke er i layout enda.
    # Nyttig når vi bruker dynamisk layout.
    suppress_callback_exceptions=True,
)

# `server` eksponeres slik at gunicorn kan starte appen:
# gunicorn app:server
server = app.server

# ---------------------------------------------------------------------------
# Layout (placeholder – erstattes med fullt dashboard i neste steg)
# ---------------------------------------------------------------------------
app.layout = html.Div(
    children=[
        html.H1("Macro Dashboard"),
        html.P(
            "Dashboard under construction. "
            "Run test_market.py to verify data fetching works."
        ),
    ],
    style={"fontFamily": "sans-serif", "padding": "2rem"},
)

# ---------------------------------------------------------------------------
# Start scheduler og appen
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Start bakgrunns-scheduler (henter data daglig + ved oppstart hvis stale)
    sched.start()

    # Railway setter PORT som miljøvariabel. Lokalt bruker vi 8050.
    port = int(os.environ.get("PORT", 8050))

    logger.info("Starting Dash app on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
