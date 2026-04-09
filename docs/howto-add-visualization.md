# Howto: Legg til en ny visualisering

> Guide for å legge til nye Dash-komponenter og Plotly-grafer i dashboardet.

---

## Dash-grunnkonsepter

Dash er bygget på to konsepter:

**Layout** – Hva som *vises*. Definert som en trestruktur av komponenter i `app.py`.
**Callbacks** – Hva som *skjer* når brukeren interagerer. Python-funksjoner dekorert med `@app.callback`.

```
Layout (HTML/komponenter)
      ↕  (bruker interagerer)
Callback (Python-funksjon)
      ↕  (returnerer ny data)
Layout oppdateres
```

---

## Legge til et nytt KPI-kort

KPI-kortene er enkle `html.Div`-blokker. Slik lager du et for en ny indikator:

```python
# I app.py

def make_kpi_card(label: str, value: float, change_pct: float) -> html.Div:
    """
    Lager et KPI-kort med fargekodet endring.

    Parameters
    ----------
    label      : Overskrift (f.eks. "S&P 500")
    value      : Siste verdi (f.eks. 5432.10)
    change_pct : Prosentvis endring (positivt = grønt, negativt = rødt)
    """
    color = "#22c55e" if change_pct >= 0 else "#ef4444"  # Tailwind green-500 / red-500
    sign = "+" if change_pct >= 0 else ""
    arrow = "▲" if change_pct >= 0 else "▼"

    return html.Div(
        className="kpi-card",
        children=[
            html.Span(label, className="kpi-label"),
            html.Span(f"{value:,.2f}", className="kpi-value"),
            html.Span(
                f"{arrow} {sign}{change_pct:.2f}%",
                style={"color": color},
                className="kpi-change",
            ),
        ],
    )
```

---

## Legge til en ny Plotly-graf

```python
import plotly.graph_objects as go
from dash import dcc

def make_line_chart(series_list: list[dict], title: str) -> dcc.Graph:
    """
    Lager en interaktiv linjegraf for en eller flere tidsserier.

    Parameters
    ----------
    series_list : Liste med kontrakt-dicts (se base.py)
    title       : Grafens tittel
    """
    fig = go.Figure()

    for series in series_list:
        dates  = [p["date"]  for p in series["series"]]
        values = [p["value"] for p in series["series"]]

        fig.add_trace(go.Scatter(
            x=dates,
            y=values,
            name=series["label"],
            mode="lines",
            hovertemplate="%{x}: %{y:,.2f}<extra></extra>",
        ))

    fig.update_layout(
        title=title,
        xaxis_title="Dato",
        yaxis_title="Verdi",
        hovermode="x unified",   # Vis alle serier på samme hover-tooltip
        template="plotly_dark",  # Mørkt tema
    )

    return dcc.Graph(figure=fig)
```

---

## Legge til en Dash-callback

Callbacks kobler brukerinteraksjon (f.eks. klikk på en knapp, valg i en dropdown)
til oppdateringer i layouten.

```python
from dash import Input, Output

@app.callback(
    Output("my-graph", "figure"),       # Hva som oppdateres
    Input("ticker-dropdown", "value"),  # Hva som trigger oppdateringen
)
def update_graph(selected_tickers: list[str]):
    """
    Oppdaterer grafen når brukeren velger andre tickers i dropdown.

    Parameters
    ----------
    selected_tickers : Liste med ticker-symboler valgt av brukeren

    Returns
    -------
    plotly.graph_objects.Figure
    """
    # Filtrer data basert på valgte tickers
    filtered = [s for s in all_series if s["ticker"] in selected_tickers]
    return make_line_chart(filtered, "Valgte indekser").figure
```

---

## Sjekkliste for ny visualisering

- [ ] Komponenten er definert som en Python-funksjon (lett å teste og gjenbruke)
- [ ] Lagt til i `app.layout` på riktig sted
- [ ] Callback er skrevet hvis komponenten skal være interaktiv
- [ ] Callback-IDs er unike (Dash krasjer ved duplikate IDs)
- [ ] Testet manuelt i nettleser
