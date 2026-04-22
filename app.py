"""
app.py
======
Inngangspunktet for macro-dashboard Dash-appen.

Layout-struktur:
  1. Header          – Tittel + sist oppdatert
  2. Indekstabell    – Kompakt klikkbar rad per ticker (e24-stil)
  3. Detaljpanel     – Vises under tabellen ved radklikk: sparkline + periodvelger
  4. Sammenlign      – Multi-ticker normalisert graf med tidsfilter

Arkitektur-notat om detaljpanel:
  Vi bruker ett fast detaljpanel (ikke inline i hver rad) fordi Dash 2.x
  ikke støtter å erstatte alle barns pattern-matched IDs via ALL-callback
  uten å krasje layout-lasteren. Detaljpanelet er alltid i DOM-en og
  oppdateres via callbacks.

Kjøres med:
    python app.py

Via gunicorn (Railway):
    gunicorn app:server
"""

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np   # noqa: F401 – pre-import før scheduler-tråd
import dash
from dash import ALL, Input, Output, State, callback, dcc, html
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
# Fargepalett
# ---------------------------------------------------------------------------
C = {
    "bg":           "#0f1117",
    "card":         "#1a1d27",
    "row_active":   "#1e2235",
    "border":       "#2a2d3a",
    "divider":      "#1f2233",
    "text":         "#e8eaf0",
    "muted":        "#8b8fa8",
    "pos":          "#22c55e",
    "neg":          "#ef4444",
    "neutral":      "#94a3b8",
    "chart_bg":     "#141720",
}

TICKER_META = {
    "OBX.OL":    {"flag": "🇳🇴", "section": "Oslo Børs"},
    "EQNR.OL":   {"flag": "🇳🇴", "section": "Oslo Børs"},
    "^GSPC":     {"flag": "🇺🇸", "section": "Globale indekser"},
    "^IXIC":     {"flag": "🇺🇸", "section": "Globale indekser"},
    "^DJI":      {"flag": "🇺🇸", "section": "Globale indekser"},
    "^GDAXI":    {"flag": "🇩🇪", "section": "Globale indekser"},
    "^FTSE":     {"flag": "🇬🇧", "section": "Globale indekser"},
    "^N225":     {"flag": "🇯🇵", "section": "Globale indekser"},
    "000001.SS": {"flag": "🇨🇳", "section": "Globale indekser"},
    "^VIX":      {"flag": "📊",  "section": "Volatilitet og råvarer"},
    "BZ=F":      {"flag": "🛢️",  "section": "Volatilitet og råvarer"},
}
SECTION_ORDER = ["Oslo Børs", "Globale indekser", "Volatilitet og råvarer"]
PERIOD_DAYS   = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365}
STORE_PATH    = Path("data/store/market.json")

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_market_data() -> list[dict]:
    """Les market.json fra disk. Tom liste hvis filen mangler."""
    if not STORE_PATH.exists():
        return []
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Feil ved innlesning av market.json: %s", exc)
        return []

# ---------------------------------------------------------------------------
# Graf-hjelpefunksjoner
# ---------------------------------------------------------------------------

def filter_by_period(series: list[dict], period: str) -> list[dict]:
    """Filtrer tidsserie til siste N dager basert på periodkode."""
    cutoff = date.today() - timedelta(days=PERIOD_DAYS.get(period, 365))
    return [p for p in series if p["date"] >= str(cutoff)]


def _hex_rgba(hex_color: str, alpha: float) -> str:
    """
    Konverter '#rrggbb' til 'rgba(r,g,b,alpha)'.

    Plotly aksepterer ikke 8-sifret hex (#rrggbbaa), men vi kan bruke
    rgba()-strenger for gjennomsiktig fyllefarge i Scatter-grafer.
    """
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def make_sparkline(entry: dict, period: str = "3M") -> go.Figure:
    """
    Kompakt linjegraf for én ticker, vist i detaljpanelet.

    Grafen viser absolutt kurs (ikke normalisert) og er laget for
    å se bra ut i en liten høyde (180px).
    """
    filtered = filter_by_period(entry["series"], period)
    if not filtered:
        return go.Figure()

    dates  = [p["date"]  for p in filtered]
    values = [p["value"] for p in filtered]
    color  = C["pos"] if values[-1] >= values[0] else C["neg"]

    fig = go.Figure(go.Scatter(
        x=dates, y=values,
        mode="lines",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=_hex_rgba(color, 0.08),   # rgba for ~8% gjennomsiktighet
        hovertemplate="%{x}: <b>%{y:,.2f}</b><extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=C["row_active"], plot_bgcolor=C["row_active"],
        margin=dict(l=48, r=16, t=8, b=28), height=300,
        xaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=10, color=C["muted"])),
        yaxis=dict(showgrid=True, gridcolor=C["divider"], zeroline=False,
                   tickfont=dict(size=10, color=C["muted"]), side="right"),
        hovermode="x unified", showlegend=False,
    )
    return fig


def make_placeholder_fig() -> go.Figure:
    """
    Tom plassholdergraf vist i høyre panel før brukeren har klikket en rad.
    Viser en sentrert tekst-hint i stedet for en tom hvit boks.
    """
    fig = go.Figure()
    fig.add_annotation(
        text="← Klikk på en indeks for å se grafen",
        xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=13, color=C["muted"]),
    )
    fig.update_layout(
        paper_bgcolor=C["card"], plot_bgcolor=C["card"],
        margin=dict(l=0, r=0, t=0, b=0), height=300,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def make_comparison_chart(market_data: list[dict],
                          selected: list[str], period: str) -> go.Figure:
    """Normalisert multi-ticker sammenlignsgraf (base = 100 ved periodestart)."""
    COLORS = ["#6366f1","#22c55e","#f59e0b","#ef4444",
              "#06b6d4","#a855f7","#f97316","#84cc16",
              "#ec4899","#14b8a6","#eab308"]
    fig = go.Figure()
    added = 0
    for e in market_data:
        if e["ticker"] not in selected:
            continue
        pts = filter_by_period(e["series"], period)
        if not pts:
            continue
        dates  = [p["date"]  for p in pts]
        values = [p["value"] for p in pts]
        base   = values[0] or 1
        normed = [round(v / base * 100, 4) for v in values]
        fig.add_trace(go.Scatter(
            x=dates, y=normed, name=e["label"],
            mode="lines",
            line=dict(color=COLORS[added % len(COLORS)], width=2),
            customdata=values,
            hovertemplate=(
                "<b>%{fullData.name}</b><br>Dato: %{x}<br>"
                "Indeks: %{y:.2f}<br>Kurs: %{customdata:,.2f}<extra></extra>"
            ),
        ))
        added += 1
    fig.add_hline(y=100, line_dash="dot", line_color=C["border"], line_width=1)
    fig.update_layout(
        paper_bgcolor=C["chart_bg"], plot_bgcolor=C["chart_bg"],
        font=dict(family="Inter, system-ui, sans-serif", color=C["text"]),
        margin=dict(l=50, r=20, t=20, b=40),
        xaxis=dict(gridcolor=C["border"], showgrid=True, zeroline=False,
                   tickfont=dict(size=11, color=C["muted"])),
        yaxis=dict(gridcolor=C["border"], showgrid=True, zeroline=False,
                   tickfont=dict(size=11, color=C["muted"]),
                   title=dict(text="Indeksert (start = 100)",
                              font=dict(size=11, color=C["muted"]))),
        legend=dict(bgcolor=C["card"], bordercolor=C["border"], borderwidth=1,
                    font=dict(size=11), orientation="h", y=-0.15),
        hovermode="x unified",
    )
    if added == 0:
        fig.add_annotation(
            text="Velg minst én indeks i dropdown-menyen over",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color=C["muted"]),
        )
    return fig

# ---------------------------------------------------------------------------
# Layout-byggere
# ---------------------------------------------------------------------------

def section_header(title: str) -> html.Div:
    return html.Div(title, style={
        "fontSize": "10px", "fontWeight": "700", "color": C["muted"],
        "letterSpacing": "0.1em", "textTransform": "uppercase",
        "padding": "12px 20px 6px 20px",
        "borderBottom": f"1px solid {C['divider']}",
    })


def ticker_row(entry: dict) -> html.Div:
    """
    Én klikkbar tabellrad.

    Raden har id={"type":"row","ticker":...} og n_clicks slik at
    handle_row_click-callbacken kan fange hvilken rad som ble klikket.
    Selve innholdet er statisk – det er ALDRI skrevet om av en callback,
    noe som unngår pattern-matched children-feil i Dash 2.x.
    """
    t    = entry["ticker"]
    last = entry["series"][-1]
    v    = last["value"]
    chg  = last["change_pct"]
    abs_ = last["change_abs"]
    flag = TICKER_META.get(t, {}).get("flag", "🌐")
    col  = C["pos"] if chg > 0 else (C["neg"] if chg < 0 else C["neutral"])
    sign = "+" if chg > 0 else ""
    arr  = "▲" if chg > 0 else ("▼" if chg < 0 else "●")

    return html.Div(
        id={"type": "row", "ticker": t},
        n_clicks=0,
        # className="ticker-row" gir grid-kolonnene; media queries i style.css
        # kan overstyre disse på smale skjermer (inline styles kan ikke det).
        className="ticker-row",
        style={
            "borderBottom": f"1px solid {C['divider']}",
        },
        children=[
            html.Span(flag, style={"fontSize": "15px"}),
            html.Span(entry["label"], style={
                "fontSize": "13px", "color": C["text"], "fontWeight": "500",
                "overflow": "hidden", "textOverflow": "ellipsis",
                "whiteSpace": "nowrap",
            }),
            html.Span(f"{v:,.2f}", style={
                "fontSize": "13px", "fontWeight": "600",
                "color": C["text"], "textAlign": "right",
                "fontVariantNumeric": "tabular-nums",
            }),
            html.Div([
                html.Span(f"{arr} {sign}{chg:.2f}%",
                          style={"fontSize": "13px", "fontWeight": "600", "color": col}),
                # className="change-abs": skjules på < 480px via style.css
                html.Span(f"  {sign}{abs_:.2f}",
                          className="change-abs",
                          style={"fontSize": "11px", "color": C["muted"]}),
            ], style={"textAlign": "right"}),
        ],
    )


def table_header() -> html.Div:
    lbl = lambda t, align="left": html.Span(t, style={   # noqa: E731
        "fontSize": "10px", "color": C["muted"], "fontWeight": "700",
        "letterSpacing": "0.08em", "textTransform": "uppercase",
        "textAlign": align,
    })
    return html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "28px 1fr 110px 120px",
        "padding": "8px 20px", "gap": "0 8px",
        "borderBottom": f"1px solid {C['border']}",
    }, children=[html.Span(), lbl("Indeks"), lbl("Siste","right"), lbl("Dag +/- %","right")])

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = dash.Dash(__name__, title="Macro Dashboard",
                suppress_callback_exceptions=True)
server = app.server


def build_layout() -> html.Div:
    """
    Bygg hele layout. Kalles ved hver sideinnlasting (funksjon, ikke objekt)
    slik at market.json alltid leses fersk.

    Layout-struktur:
    ┌─────────────────────────────────────────────────────┐
    │  Header                                             │
    ├────────────────────────┬────────────────────────────┤
    │  Indekstabell (venstre)│  Detaljgraf (høyre, sticky)│
    │  – klikkbare rader     │  – oppdateres ved klikk    │
    ├────────────────────────┴────────────────────────────┤
    │  Sammenlign-seksjon (full bredde)                   │
    └─────────────────────────────────────────────────────┘
    """
    market_data    = load_market_data()
    data_by_ticker = {e["ticker"]: e for e in market_data}

    ts = market_data[0].get("last_updated", "")[:16].replace("T", " ") + " UTC" \
         if market_data else ""

    # Standardvalg: vis OBX eller første tilgjengelige ticker ved oppstart
    default_active = next(
        (t for t in ["OBX.OL", "^GSPC"] if t in data_by_ticker),
        market_data[0]["ticker"] if market_data else None,
    )

    # Sammenlign-graf: standard tre indekser
    default_compare = [t for t in ["^GSPC", "OBX.OL", "^IXIC"]
                       if t in data_by_ticker] or \
                      ([market_data[0]["ticker"]] if market_data else [])
    dropdown_opts = [{"label": e["label"], "value": e["ticker"]}
                     for e in market_data]

    # Bygg tabellrader gruppert per seksjon
    rows: list = [table_header()]
    for sec in SECTION_ORDER:
        entries = [e for e in market_data
                   if TICKER_META.get(e["ticker"], {}).get("section") == sec]
        if not entries:
            continue
        rows.append(section_header(sec))
        for e in entries:
            rows.append(ticker_row(e))

    period_btn = lambda val: {"label": val, "value": val}   # noqa: E731

    # Forhåndsvis detaljer for standardvalgt ticker (siden vi setter data=default_active)
    default_entry  = data_by_ticker.get(default_active)
    default_fig    = make_sparkline(default_entry, "3M") if default_entry else make_placeholder_fig()
    if default_entry:
        last = default_entry["series"][-1]
        chg  = last["change_pct"]
        sign = "+" if chg > 0 else ""
        col  = C["pos"] if chg > 0 else C["neg"]
        default_title = html.Div([
            html.Span(default_entry["label"],
                      style={"fontWeight": "700", "marginRight": "10px"}),
            html.Span(f"{last['value']:,.2f}",
                      style={"marginRight": "10px", "fontVariantNumeric": "tabular-nums"}),
            html.Span(f"{sign}{chg:.2f}%", style={"color": col, "fontWeight": "600"}),
        ])
    else:
        default_title = ""

    return html.Div(
        style={"background": C["bg"], "minHeight": "100vh",
               "fontFamily": "Inter, system-ui, sans-serif", "color": C["text"]},
        children=[
            # ── Header ────────────────────────────────────────────────────
            # className="site-header" – flex-wrap og padding styres av style.css
            html.Div(className="site-header", style={
                "borderBottom": f"1px solid {C['border']}",
            }, children=[
                html.Div([
                    html.H1("Macro Dashboard", style={
                        "margin": "0", "fontSize": "20px",
                        "fontWeight": "700", "letterSpacing": "-0.02em",
                    }),
                    html.Span("Børsdata via Yahoo Finance · EOD",
                              style={"fontSize": "12px", "color": C["muted"]}),
                ]),
                html.Div(f"Oppdatert: {ts}" if ts else "Ingen data",
                         style={"fontSize": "12px", "color": C["muted"]}),
            ]),

            # ── Hovedinnhold ──────────────────────────────────────────────
            # className="main-content" brukes av style.css for responsiv padding.
            html.Div(className="main-content", children=[

                # ── To-kolonne: tabell | detaljgraf ───────────────────────
                # className="main-grid": to kolonner på ≥800px, én på <800px.
                # Selve grid-stilene (display/columns/gap) ligger i style.css
                # slik at media queries kan overstyre dem – inline styles kan
                # ikke overrides av media queries.
                html.Div(className="main-grid", children=[

                    # ── Venstre: indekstabell ─────────────────────────────
                    html.Div(
                        id="index-table",
                        style={"background": C["card"],
                               "border": f"1px solid {C['border']}",
                               "borderRadius": "12px", "overflow": "hidden"},
                        children=rows,
                    ),

                    # ── Høyre: detaljgraf (alltid synlig) ──────────────────
                    # className="detail-panel-col": sticky på desktop, relativt
                    # på mobil (se style.css). Ingen show/hide – panelet er
                    # alltid i DOM. Callbacks oppdaterer kun tittel og figur.
                    html.Div(
                        id="detail-panel",
                        className="detail-panel-col",
                        style={
                            "background": C["card"],
                            "border": f"1px solid {C['border']}",
                            "borderRadius": "12px",
                            "padding": "20px",
                            # position og top settes av style.css / media query
                        },
                        children=[
                            # Tittellinje: label + kurs + daglig endring
                            html.Div(id="detail-title",
                                     children=default_title,
                                     style={
                                         "fontSize": "14px", "fontWeight": "600",
                                         "color": C["text"], "marginBottom": "14px",
                                         "minHeight": "20px",
                                     }),
                            # Periodvelger
                            dcc.RadioItems(
                                id="detail-period",
                                options=[period_btn(k) for k in PERIOD_DAYS],
                                value="3M",
                                inline=True,
                                inputStyle={"display": "none"},
                                labelStyle={
                                    "display": "inline-block",
                                    "padding": "4px 12px", "marginRight": "4px",
                                    "borderRadius": "5px",
                                    "border": f"1px solid {C['border']}",
                                    "cursor": "pointer", "fontSize": "11px",
                                    "fontWeight": "600", "color": C["muted"],
                                },
                                style={"marginBottom": "12px"},
                            ),
                            # Sparkline-graf
                            dcc.Graph(
                                id="detail-graph",
                                figure=default_fig,
                                config={"displayModeBar": False},
                                style={"height": "300px"},
                            ),
                        ],
                    ),
                ]),

                # ── Sammenlign-seksjon (full bredde under to-kolonne) ──────
                html.Div("📈  SAMMENLIGN INDEKSER", style={
                    "fontSize": "11px", "fontWeight": "700", "color": C["muted"],
                    "letterSpacing": "0.1em", "textTransform": "uppercase",
                    "marginBottom": "12px", "paddingBottom": "8px",
                    "borderBottom": f"1px solid {C['border']}",
                }),
                html.Div(style={
                    "background": C["card"], "border": f"1px solid {C['border']}",
                    "borderRadius": "12px", "padding": "20px 24px",
                }, children=[
                    html.Div(style={
                        "display": "flex", "gap": "16px", "alignItems": "center",
                        "flexWrap": "wrap", "marginBottom": "20px",
                    }, children=[
                        html.Div(
                            dcc.Dropdown(
                                id="compare-dropdown",
                                options=dropdown_opts,
                                value=default_compare,
                                multi=True,
                                placeholder="Velg indekser...",
                                style={"fontSize": "13px"},
                            ),
                            style={"flex": "1", "minWidth": "260px"},
                        ),
                        dcc.RadioItems(
                            id="compare-period",
                            options=[period_btn(k) for k in PERIOD_DAYS],
                            value="1Y", inline=True,
                            inputStyle={"display": "none"},
                            labelStyle={
                                "display": "inline-block", "padding": "5px 14px",
                                "marginRight": "4px", "borderRadius": "6px",
                                "border": f"1px solid {C['border']}",
                                "cursor": "pointer", "fontSize": "12px",
                                "fontWeight": "600", "color": C["muted"],
                            },
                        ),
                    ]),
                    dcc.Graph(
                        id="compare-chart",
                        figure=make_comparison_chart(market_data, default_compare, "1Y"),
                        config={"displayModeBar": True,
                                "modeBarButtonsToRemove": ["select2d","lasso2d"],
                                "displaylogo": False},
                        style={"height": "420px"},
                    ),
                ]),

                html.Div(
                    "Data: Yahoo Finance (EOD) · Oslo Børs: OBX.OL og EQNR.OL",
                    style={"marginTop": "16px", "fontSize": "11px",
                           "color": C["muted"], "textAlign": "center"},
                ),
            ]),

            # ── State ─────────────────────────────────────────────────────
            # Sett default_active slik at grafen vises med en gang på oppstart
            dcc.Store(id="active-ticker", data=default_active),
            dcc.Interval(id="refresh-interval", interval=5*60*1000, n_intervals=0),
        ],
    )


app.layout = build_layout

# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("active-ticker", "data"),
    Input({"type": "row", "ticker": ALL}, "n_clicks"),
    State("active-ticker", "data"),
    prevent_initial_call=True,
)
def handle_row_click(all_clicks, current):
    """
    Oppdater aktiv ticker ved radklikk.
    Klikk på samme rad igjen lukker detaljpanelet (toggle).
    """
    triggered = dash.ctx.triggered_id
    if not triggered:
        return current
    clicked = triggered.get("ticker")
    return None if clicked == current else clicked


@callback(
    Output({"type": "row", "ticker": ALL}, "style"),
    Input("active-ticker", "data"),
    Input({"type": "row", "ticker": ALL}, "n_clicks"),  # kun for å hente ticker-rekkefølge
    prevent_initial_call=False,
)
def highlight_active_row(active, _clicks):
    """
    Sett bakgrunn på aktiv rad. Alle andre rader er gjennomsiktige.
    Endrer kun 'background' – layout og grid forblir uendret.

    Vi legger til n_clicks-input bare for å kunne lese tickers via
    ctx.inputs_list[1], siden outputs_list-formatet varierer mellom
    Dash-versjoner. inputs_list er stabilt og pålitelig.
    """
    # inputs_list[1] = liste av pattern-matched n_clicks-specs.
    # Hver spec: {"id": {"type": "row", "ticker": <t>}, "property": "n_clicks", ...}
    tickers = [s["id"]["ticker"] for s in dash.ctx.inputs_list[1]]

    # Vi setter kun background her – grid-layout og padding bor i className
    # "ticker-row" (style.css) og kan dermed overstyres av media queries.
    return [
        {
            "borderBottom": f"1px solid {C['divider']}",
            "background": C["row_active"] if t == active else "transparent",
        }
        for t in tickers
    ]


@callback(
    Output("detail-title", "children"),
    Output("detail-graph", "figure"),
    Input("active-ticker", "data"),
    Input("detail-period", "value"),
    prevent_initial_call=False,
)
def update_detail_panel(active, period):
    """
    Oppdater tittel og sparkline-graf i høyre detaljpanel.

    Panelet er alltid synlig (to-kolonne-layout) – vi trenger ikke
    lenger å vise/skjule det. Kalles ved radklikk og periodbytte.

    Hvis ingen ticker er valgt: vis plassholder-figur.
    """
    if not active:
        return "", make_placeholder_fig()

    market_data    = load_market_data()
    data_by_ticker = {e["ticker"]: e for e in market_data}

    if active not in data_by_ticker:
        return "", make_placeholder_fig()

    entry = data_by_ticker[active]
    last  = entry["series"][-1]
    chg   = last["change_pct"]
    sign  = "+" if chg > 0 else ""
    col   = C["pos"] if chg > 0 else C["neg"]

    title = html.Div([
        html.Span(entry["label"],
                  style={"fontWeight": "700", "marginRight": "10px"}),
        html.Span(f"{last['value']:,.2f}",
                  style={"marginRight": "10px", "fontVariantNumeric": "tabular-nums"}),
        html.Span(f"{sign}{chg:.2f}%", style={"color": col, "fontWeight": "600"}),
    ])

    return title, make_sparkline(entry, period)


@callback(
    Output("compare-chart", "figure"),
    Input("compare-dropdown", "value"),
    Input("compare-period",   "value"),
    prevent_initial_call=True,
)
def update_compare_chart(selected, period):
    """Oppdater sammenlign-grafen ved valg av ticker eller periode."""
    return make_comparison_chart(load_market_data(), selected or [], period)


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
sched.start()
Path("data/store").mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    logger.info("Starting Dash app on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
