"""Plotly figure builders. Data shaping lives in fare_analysis.py."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import fare_analysis as fa

PALETTE = ["#0B2545", "#1565D8", "#00A3A3", "#E08A00", "#8E5AD8", "#C2410C", "#4B5563"]
FONT = "Public Sans, system-ui, -apple-system, Segoe UI, sans-serif"


def build_trend_chart(df: pd.DataFrame, mode: str = "routes", currency: str = "PKR") -> go.Figure:
    """Line chart of fares over observation date.

    mode="routes":   one line per route (average of the selected fares) - comparison view.
    mode="airlines": one line per airline for the routes in ``df`` - detail view.
    Dates are sorted chronologically; missing fares leave visible gaps (connectgaps=False).
    """
    fig = go.Figure()
    if mode == "airlines":
        data = fa.daily_airline_average(df).sort_values("recorded_at")
        for i, (airline, g) in enumerate(data.groupby("airline", sort=True)):
            fig.add_trace(go.Scatter(
                x=g["recorded_at"], y=g["avg_fare"], name=airline, mode="lines+markers",
                line=dict(color=PALETTE[i % len(PALETTE)], width=2.2), marker=dict(size=5),
                connectgaps=False,
                customdata=g[["quotes", "sources", "route"]].to_numpy(),
                hovertemplate=(
                    "<b>%{customdata[2]}</b><br>Airline: %{fullData.name}<br>"
                    "Observed: %{x|%d %b %Y}<br>Avg fare: " + currency + " %{y:,.0f}<br>"
                    "Fares averaged: %{customdata[0]}<br>Source: %{customdata[1]}<extra></extra>"
                ),
            ))
    else:
        data = fa.daily_route_average(df).sort_values("recorded_at")
        for i, (route, g) in enumerate(data.groupby("route", sort=True)):
            fig.add_trace(go.Scatter(
                x=g["recorded_at"], y=g["avg_fare"], name=route, mode="lines+markers",
                line=dict(color=PALETTE[i % len(PALETTE)], width=2.2), marker=dict(size=5),
                connectgaps=False,
                customdata=g[["quotes", "airlines", "sources"]].to_numpy(),
                hovertemplate=(
                    "<b>Route: %{fullData.name}</b><br>Observed: %{x|%d %b %Y}<br>"
                    "Avg fare: " + currency + " %{y:,.0f}<br>Airlines: %{customdata[1]}<br>"
                    "Fares averaged: %{customdata[0]}<br>Source: %{customdata[2]}<extra></extra>"
                ),
            ))
    fig.update_layout(
        template="plotly_white",
        font=dict(family=FONT, size=13, color="#14213D"),
        height=470,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        xaxis=dict(title="Observation date", showgrid=False, tickformat="%d %b %Y", automargin=True),
        yaxis=dict(title=f"Fare ({currency})", tickformat=",.0f", gridcolor="#E3EBF7", automargin=True,
                   rangemode="tozero"),
    )
    return fig
