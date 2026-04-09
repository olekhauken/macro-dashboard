"""
app.py
======
Inngangspunktet for macro-dashboard Dash-appen.

Layout-struktur:
  1. Header            – Tittel + sist oppdatert
  2. Oslo Børs-seksjon – KPI-kort for OSEBX og OBX øverst
  3. Globale indekser  – KPI-kort for alle globale indekser
  4. Annet             – VIX og Brent crude
  5. Graf-seksjon      – Interaktiv tidsserie med:
       - Multi-select dropdown for tickers
       - Tidsfilter (1V / 1M / 3M / 6M / 1Y)

Kjøres med:
    python app.py

Eller via gunicorn (Railway):
    gunicorn app:server
"""

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import dash
from dash import Input, Output, callback, dcc, html
import plotly.graph_objects as go

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
# Fargepalett  (brukes konsekvent gjennom hele layoutet)
# ---------------------------------------------------------------------------
COLORS = {
    "bg":           "#0f1117",   # Mørk bakgrunn – hele siden
    "card_bg":      "#1a1d27",   # Kortbakgrunn
    "card_border":  "#2a2d3a",   # Kortramme
    "text_primary": "#e8eaf0",   # Hovedtekst
    "text_muted":   "#8b8fa8",   # Sekundærtekst / labels
    "positive":     "#22c55e",   # Grønn – positiv endring
    "negative":     "#ef4444",   # Rød – negativ endring
    "neutral":      "#94a3b8",   # Grå – ingen endring / mangler
    "accent":       "#6366f1",   # Indigo – aksentfarge
    "chart_bg":     "#141720",   # Grafbakgrunn
}

# ---------------------------------------------------------------------------
# Data-innlesning
# ---------------------------------------------------------------------------
STORE_PATH = Path("data/store/market.json")


def load_market_data() -> list[dict]:
    """
    Les market.json fra disk og returner listen med ticker-dicts.

    Returns
    -------
    list[dict]
        Tom liste hvis filen ikke finnes ennå (første oppstart).
    """
    if not STORE_PATH.exists():
        logger.warning("market.json ikke funnet – ingen data å vise enda.")
        return []
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Feil ved innlesning av market.json: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Hjelpefunksjoner for KPI-kort
# ---------------------------------------------------------------------------

def fmt_value(value: float, ticker: str) -> str:
    """
    Formater en kursverdi passende for visning.
    VIX og Brent vises med 2 desimaler, indekser med 0 desimaler over 1000.
    """
    if value < 100:
        return f"{value:,.2f}"
    return f"{value:,.2f}"


def make_kpi_card(entry: dict) -> html.Div:
    """
    Bygg et KPI-kort for én ticker.

    Kortet viser:
    - Ticker-navn (label)
    - Siste kurs
    - Absolutt endring og prosentvis endring (fargekodet)

    Parameters
    ----------
    entry : dict
        Et kontrakt-dict fra market.json (se base.py).

    Returns
    -------
    html.Div
        Et Dash-HTML-element som representerer KPI-kortet.
    """
    last = entry["series"][-1]
    value = last["value"]
    change_abs = last["change_abs"]
    change_pct = last["change_pct"]

    # Velg farge og pil basert på om endringen er positiv eller negativ
    if change_pct > 0:
        color = COLORS["positive"]
        arrow = "▲"
        sign = "+"
    elif change_pct < 0:
        color = COLORS["negative"]
        arrow = "▼"
        sign = ""
    else:
        color = COLORS["neutral"]
        arrow = "●"
        sign = ""

    return html.Div(
        className="kpi-card",
        style={
            "background":    COLORS["card_bg"],
            "border":        f"1px solid {COLORS['card_border']}",
            "borderRadius":  "10px",
            "padding":       "16px 20px",
            "minWidth":      "170px",
            "flex":          "1",
        },
        children=[
            # Tickernavn øverst
            html.Div(
                entry["label"],
                style={
                    "fontSize":   "11px",
                    "color":      COLORS["text_muted"],
                    "fontWeight": "600",
                    "letterSpacing": "0.05em",
                    "textTransform": "uppercase",
                    "marginBottom": "8px",
                    "whiteSpace": "nowrap",
                    "overflow": "hidden",
                    "textOverflow": "ellipsis",
                },
            ),
            # Siste kurs (stor tekst)
            html.Div(
                fmt_value(value, entry["ticker"]),
                style={
                    "fontSize":   "22px",
                    "fontWeight": "700",
                    "color":      COLORS["text_primary"],
                    "marginBottom": "6px",
                    "letterSpacing": "-0.02em",
                },
            ),
            # Endring (fargekodet)
            html.Div(
                style={"display": "flex", "gap": "6px", "alignItems": "center"},
                children=[
                    html.Span(
                        f"{arrow} {sign}{change_pct:.2f}%",
                        style={"color": color, "fontSize": "13px", "fontWeight": "600"},
                    ),
                    html.Span(
                        f"({sign}{change_abs:,.2f})",
                        style={"color": COLORS["text_muted"], "fontSize": "12px"},
                    ),
                ],
            ),
        ],
    )


def make_unavailable_card(label: str, ticker: str) -> html.Div:
    """
    Bygg et grået ut KPI-kort for tickers uten tilgjengelige data.
    Brukes primært for OSEBX og OBX som av og til mangler fra Yahoo Finance.
    """
    return html.Div(
        style={
            "background":   COLORS["card_bg"],
            "border":       f"1px solid {COLORS['card_border']}",
            "borderRadius": "10px",
            "padding":      "16px 20px",
            "minWidth":     "170px",
            "flex":         "1",
            "opacity":      "0.5",
        },
        children=[
            html.Div(
                label,
                style={
                    "fontSize": "11px", "color": COLORS["text_muted"],
                    "fontWeight": "600", "letterSpacing": "0.05em",
                    "textTransform": "uppercase", "marginBottom": "8px",
                },
            ),
            html.Div(
                "–",
                style={"fontSize": "22px", "fontWeight": "700",
                       "color": COLORS["text_muted"], "marginBottom": "6px"},
            ),
            html.Div(
                "Ikke tilgjengelig",
                style={"fontSize": "12px", "color": COLORS["text_muted"]},
            ),
        ],
    )


def make_section_header(title: str) -> html.Div:
    """Lager en seksjonstittel med understrek."""
    return html.Div(
        title,
        style={
            "fontSize":      "11px",
            "fontWeight":    "700",
            "color":         COLORS["text_muted"],
            "letterSpacing": "0.1em",
            "textTransform": "uppercase",
            "marginBottom":  "12px",
            "paddingBottom": "8px",
            "borderBottom":  f"1px solid {COLORS['card_border']}",
        },
    )


# ---------------------------------------------------------------------------
# Graf-hjelpefunksjoner
# ---------------------------------------------------------------------------

PERIOD_DAYS = {
    "1W":  7,
    "1M":  30,
    "3M":  90,
    "6M":  180,
    "1Y":  365,
}


def filter_series_by_period(series: list[dict], period: str) -> list[dict]:
    """
    Filtrer en tidsserie til siste N dager basert på valgt periode.

    Parameters
    ----------
    series : list[dict]
        Full tidsserie fra kontrakt-dict.
    period : str
        En av "1W", "1M", "3M", "6M", "1Y".

    Returns
    -------
    list[dict]
        Filtrert tidsserie.
    """
    days = PERIOD_DAYS.get(period, 365)
    cutoff = date.today() - timedelta(days=days)
    return [p for p in series if p["date"] >= str(cutoff)]


def make_chart(market_data: list[dict], selected_tickers: list[str], period: str) -> go.Figure:
    """
    Bygg en interaktiv Plotly-linjegraf for valgte tickers og tidsperiode.

    For å gjøre det enkelt å sammenligne indekser med svært ulike kursnivåer
    (f.eks. OSEBX ~1400 vs Nikkei ~38000) normaliseres alle serier til 100
    ved startpunktet for valgt periode.

    Parameters
    ----------
    market_data : list[dict]
        Alle tilgjengelige ticker-dicts fra market.json.
    selected_tickers : list[str]
        Ticker-symboler valgt av brukeren i dropdown.
    period : str
        Valgt tidsperiode ("1W", "1M", "3M", "6M", "1Y").

    Returns
    -------
    plotly.graph_objects.Figure
    """
    fig = go.Figure()

    # Fargesekvens for linjene – bruker en pen blå-til-grønn gradient
    line_colors = [
        "#6366f1", "#22c55e", "#f59e0b", "#ef4444",
        "#06b6d4", "#a855f7", "#f97316", "#84cc16",
        "#ec4899", "#14b8a6", "#eab308",
    ]

    added = 0
    for entry in market_data:
        if entry["ticker"] not in selected_tickers:
            continue

        filtered = filter_series_by_period(entry["series"], period)
        if not filtered:
            continue

        dates  = [p["date"]  for p in filtered]
        values = [p["value"] for p in filtered]

        # Normaliser til 100 ved periodens startpunkt slik at ulike indeksnivåer
        # kan sammenlignes direkte på én akse.
        base = values[0] if values[0] != 0 else 1
        normalized = [round(v / base * 100, 4) for v in values]

        fig.add_trace(go.Scatter(
            x=dates,
            y=normalized,
            name=entry["label"],
            mode="lines",
            line=dict(
                color=line_colors[added % len(line_colors)],
                width=2,
            ),
            # Hover viser både normalisert verdi OG faktisk kurs
            customdata=values,
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Dato: %{x}<br>"
                "Indeks (norm.): %{y:.2f}<br>"
                "Faktisk kurs: %{customdata:,.2f}"
                "<extra></extra>"
            ),
        ))
        added += 1

    # Horisontal referanselinje ved 100 (startverdi)
    fig.add_hline(
        y=100,
        line_dash="dot",
        line_color=COLORS["card_border"],
        line_width=1,
    )

    fig.update_layout(
        paper_bgcolor=COLORS["chart_bg"],
        plot_bgcolor=COLORS["chart_bg"],
        font=dict(family="Inter, system-ui, sans-serif", color=COLORS["text_primary"]),
        margin=dict(l=50, r=20, t=20, b=40),
        xaxis=dict(
            gridcolor=COLORS["card_border"],
            showgrid=True,
            zeroline=False,
            tickfont=dict(size=11, color=COLORS["text_muted"]),
        ),
        yaxis=dict(
            gridcolor=COLORS["card_border"],
            showgrid=True,
            zeroline=False,
            tickfont=dict(size=11, color=COLORS["text_muted"]),
            ticksuffix="",
            title=dict(
                text="Indeksert (start = 100)",
                font=dict(size=11, color=COLORS["text_muted"]),
            ),
        ),
        legend=dict(
            bgcolor=COLORS["card_bg"],
            bordercolor=COLORS["card_border"],
            borderwidth=1,
            font=dict(size=11),
            orientation="h",
            y=-0.15,
        ),
        hovermode="x unified",
    )

    if added == 0:
        fig.add_annotation(
            text="Velg minst én indeks i dropdown-menyen over",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14, color=COLORS["text_muted"]),
        )

    return fig


# ---------------------------------------------------------------------------
# Dash-app
# ---------------------------------------------------------------------------
app = dash.Dash(
    __name__,
    title="Macro Dashboard",
    suppress_callback_exceptions=True,
)
server = app.server   # Eksponert for gunicorn: gunicorn app:server


def build_layout() -> html.Div:
    """
    Bygg hele dashboardlayouten.

    Layouten leses på nytt ved kall (ikke bare ved oppstart), slik at data
    fra market.json alltid er fersk når siden lastes.

    Returns
    -------
    html.Div
        Rot-elementet for Dash-appen.
    """
    market_data = load_market_data()

    # Lag et oppslagsdikt: ticker → entry (for rask tilgang i KPI-seksjonene)
    data_by_ticker = {e["ticker"]: e for e in market_data}

    # Definer hvilke tickers som hører til hvilke seksjoner
    oslo_tickers   = [("^OSEBX", "Oslo Børs – OSEBX"), ("^OBX", "Oslo Børs – OBX 25")]
    global_tickers = [
        ("^GSPC", "S&P 500"), ("^IXIC", "NASDAQ Composite"), ("^DJI", "Dow Jones"),
        ("^GDAXI", "DAX"),    ("^FTSE", "FTSE 100"),          ("^N225", "Nikkei 225"),
        ("000001.SS", "Shanghai Composite"),
    ]
    other_tickers  = [("^VIX", "VIX – Volatility Index"), ("BZ=F", "Brent Crude Oil")]

    def kpi_row(ticker_list: list[tuple]) -> html.Div:
        """Bygg en rad med KPI-kort for en liste av (ticker, label)-tupler."""
        cards = []
        for ticker, label in ticker_list:
            if ticker in data_by_ticker:
                cards.append(make_kpi_card(data_by_ticker[ticker]))
            else:
                cards.append(make_unavailable_card(label, ticker))
        return html.Div(
            cards,
            style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "12px",
                "marginBottom": "12px",
            },
        )

    # Dropdown-alternativer for grafen – kun tickers med data
    dropdown_options = [
        {"label": e["label"], "value": e["ticker"]}
        for e in market_data
    ]

    # Standardvalg: S&P 500 + OSEBX (hvis tilgjengelig), ellers første to
    default_selection = []
    for pref in ["^GSPC", "^OSEBX", "^IXIC"]:
        if pref in data_by_ticker:
            default_selection.append(pref)
        if len(default_selection) == 3:
            break
    if not default_selection and market_data:
        default_selection = [market_data[0]["ticker"]]

    # Sist oppdatert-tidsstempel fra første tilgjengelige entry
    last_updated = ""
    if market_data:
        ts = market_data[0].get("last_updated", "")
        if ts:
            last_updated = ts[:16].replace("T", " ") + " UTC"

    return html.Div(
        style={
            "background":   COLORS["bg"],
            "minHeight":    "100vh",
            "fontFamily":   "Inter, system-ui, sans-serif",
            "color":        COLORS["text_primary"],
        },
        children=[
            # ---- Header ----
            html.Div(
                style={
                    "borderBottom": f"1px solid {COLORS['card_border']}",
                    "padding":      "20px 32px",
                    "display":      "flex",
                    "justifyContent": "space-between",
                    "alignItems":   "center",
                },
                children=[
                    html.Div([
                        html.H1(
                            "Macro Dashboard",
                            style={
                                "margin": "0", "fontSize": "20px",
                                "fontWeight": "700", "color": COLORS["text_primary"],
                                "letterSpacing": "-0.02em",
                            },
                        ),
                        html.Span(
                            "Børsdata via Yahoo Finance · EOD",
                            style={"fontSize": "12px", "color": COLORS["text_muted"]},
                        ),
                    ]),
                    html.Div(
                        f"Oppdatert: {last_updated}" if last_updated else "Ingen data",
                        style={"fontSize": "12px", "color": COLORS["text_muted"]},
                    ),
                ],
            ),

            # ---- Innhold ----
            html.Div(
                style={"padding": "28px 32px"},
                children=[

                    # Oslo Børs
                    make_section_header("🇳🇴  Oslo Børs"),
                    kpi_row(oslo_tickers),

                    # Globale indekser
                    html.Div(style={"marginTop": "24px"}),
                    make_section_header("🌍  Globale indekser"),
                    kpi_row(global_tickers),

                    # Annet
                    html.Div(style={"marginTop": "24px"}),
                    make_section_header("📊  Volatilitet og råvarer"),
                    kpi_row(other_tickers),

                    # Graf
                    html.Div(style={"marginTop": "32px"}),
                    make_section_header("📈  Sammenlign indekser"),
                    html.Div(
                        style={
                            "background":    COLORS["card_bg"],
                            "border":        f"1px solid {COLORS['card_border']}",
                            "borderRadius":  "12px",
                            "padding":       "20px 24px",
                        },
                        children=[
                            # Kontroller: dropdown + tidsfilter
                            html.Div(
                                style={
                                    "display":        "flex",
                                    "gap":            "16px",
                                    "alignItems":     "center",
                                    "flexWrap":       "wrap",
                                    "marginBottom":   "20px",
                                },
                                children=[
                                    # Multi-select ticker dropdown
                                    html.Div(
                                        style={"flex": "1", "minWidth": "260px"},
                                        children=[
                                            dcc.Dropdown(
                                                id="ticker-dropdown",
                                                options=dropdown_options,
                                                value=default_selection,
                                                multi=True,
                                                placeholder="Velg indekser...",
                                                style={"fontSize": "13px"},
                                            ),
                                        ],
                                    ),
                                    # Tidsfilter-knapper
                                    html.Div(
                                        dcc.RadioItems(
                                            id="period-radio",
                                            options=[
                                                {"label": k, "value": k}
                                                for k in PERIOD_DAYS
                                            ],
                                            value="1Y",
                                            inline=True,
                                            inputStyle={"display": "none"},  # Skjul radio-sirkel
                                            labelStyle={
                                                "display":       "inline-block",
                                                "padding":       "5px 14px",
                                                "marginRight":   "4px",
                                                "borderRadius":  "6px",
                                                "border":        f"1px solid {COLORS['card_border']}",
                                                "cursor":        "pointer",
                                                "fontSize":      "12px",
                                                "fontWeight":    "600",
                                                "color":         COLORS["text_muted"],
                                                "letterSpacing": "0.03em",
                                            },
                                        ),
                                    ),
                                ],
                            ),
                            # Selve grafen
                            dcc.Graph(
                                id="market-chart",
                                figure=make_chart(market_data, default_selection, "1Y"),
                                config={
                                    "displayModeBar": True,
                                    "modeBarButtonsToRemove": [
                                        "select2d", "lasso2d", "autoScale2d",
                                    ],
                                    "displaylogo": False,
                                },
                                style={"height": "420px"},
                            ),
                        ],
                    ),

                    # Fotnote
                    html.Div(
                        "Data: Yahoo Finance (EOD) · Indekser normalisert til 100 ved periodens start · "
                        "OSEBX/OBX kan mangle utenfor norsk åpningstid",
                        style={
                            "marginTop":  "16px",
                            "fontSize":   "11px",
                            "color":      COLORS["text_muted"],
                            "textAlign":  "center",
                        },
                    ),
                ],
            ),

            # dcc.Interval oppdaterer layouten automatisk hvert 5. minutt
            # (nyttig når appen kjører lenge og markedet er åpent)
            dcc.Interval(id="refresh-interval", interval=5 * 60 * 1000, n_intervals=0),
        ],
    )


# Vi bruker en funksjon for layout (ikke et fast objekt) slik at siden
# re-leser market.json hver gang nettleseren laster siden på nytt.
app.layout = build_layout


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("market-chart", "figure"),
    Input("ticker-dropdown", "value"),
    Input("period-radio",    "value"),
    prevent_initial_call=True,
)
def update_chart(selected_tickers: list[str], period: str) -> go.Figure:
    """
    Oppdater grafen når brukeren velger andre tickers eller tidsperiode.

    Kalles automatisk av Dash når input-verdiene endres.

    Parameters
    ----------
    selected_tickers : list[str]
        Ticker-symboler valgt i dropdown (f.eks. ["^GSPC", "^IXIC"]).
    period : str
        Valgt tidsperiode ("1W", "1M", "3M", "6M", "1Y").

    Returns
    -------
    plotly.graph_objects.Figure
        Oppdatert graf.
    """
    if not selected_tickers:
        selected_tickers = []

    market_data = load_market_data()
    return make_chart(market_data, selected_tickers, period)


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sched.start()
    port = int(os.environ.get("PORT", 8050))
    logger.info("Starting Dash app on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
