"""Data loading, validation and calculations for the Travel.pk Flight Price Trend Analyzer.

This module imports only pandas and the standard library, so it can be unit-tested
without Streamlit or Plotly. The UI (app.py) and charts (charts.py) call into it.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

DATA_FILENAME = "data/flight_fares.csv"
DATA_PATH = Path(__file__).resolve().parent / "data" / "flight_fares.csv"

REQUIRED_COLUMNS = [
    "recorded_at",
    "origin",
    "origin_code",
    "destination",
    "destination_code",
    "airline",
    "departure_date",
    "fare",
    "currency",
    "source",
    "is_simulated",
]

REQUIRED_ROUTES = [("LHE", "KHI"), ("KHI", "ISB"), ("LHE", "ISB"), ("LHE", "DXB"), ("ISB", "DXB")]

DEMO_NOTICE = "DEMO DATA — These fares are simulated for demonstration and are not live airline prices."

MIN_DATES_FOR_TREND = 5   # fewer distinct observation dates than this -> reliability warning
SMALL_SAMPLE = 30         # fewer priced observations than this -> small-sample warning

COMPARISON_COLUMNS = [
    "Route",
    "Observations",
    "Min fare",
    "Avg fare",
    "Max fare",
    "First observation",
    "Last observation",
    "Change (matched fares)",
    "Matched fares",
]

_TRUE = ["true", "1", "yes", "y", "t"]
_FALSE = ["false", "0", "no", "n", "f"]


class DatasetError(ValueError):
    """Raised when the CSV cannot be used (missing columns, bad dates, ...)."""


# --------------------------------------------------------------------------- loading
def _parse_bool(series: pd.Series) -> pd.Series:
    lowered = series.str.strip().str.lower()
    unknown = ~lowered.isin(_TRUE + _FALSE)
    if unknown.any():
        raise DatasetError(f"{int(unknown.sum())} value(s) in 'is_simulated' are not true/false.")
    return lowered.isin(_TRUE)


def load_dataset(path: Path | str = DATA_PATH) -> tuple[pd.DataFrame, dict]:
    """Load, validate and clean the fare CSV.

    Returns (dataframe, report). The report counts every cleaning action so the
    methodology page can show exactly what happened.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    raw.columns = [c.strip() for c in raw.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise DatasetError("Missing required column(s): " + ", ".join(missing))
    if raw.empty:
        raise DatasetError("The dataset contains no rows.")

    df = raw[REQUIRED_COLUMNS].copy()
    for col in df.columns:
        df[col] = df[col].str.strip()

    for col in ("origin", "origin_code", "destination", "destination_code", "airline", "currency", "source"):
        if (df[col] == "").any():
            raise DatasetError(f"Column '{col}' has empty values.")

    for col in ("recorded_at", "departure_date"):
        parsed = pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce")
        bad = int(parsed.isna().sum())
        if bad:
            raise DatasetError(f"{bad} value(s) in '{col}' are not valid YYYY-MM-DD dates.")
        df[col] = parsed

    df["origin_code"] = df["origin_code"].str.upper()
    df["destination_code"] = df["destination_code"].str.upper()
    df["currency"] = df["currency"].str.upper()
    df["is_simulated"] = _parse_bool(df["is_simulated"])

    # Fares: blank = missing; non-numeric, zero, negative or infinite = invalid (set to missing).
    blank = df["fare"] == ""
    fare = pd.to_numeric(df["fare"], errors="coerce")
    bad_value = (~blank) & (fare.isna() | (fare <= 0) | fare.isin([float("inf"), float("-inf")]))
    df["fare"] = fare.mask(bad_value).astype(float)

    rows_read = len(df)

    late = df["recorded_at"] > df["departure_date"]
    df = df.loc[~late]

    key = ["recorded_at", "origin_code", "destination_code", "airline", "departure_date"]
    dup = df.duplicated(subset=key, keep="first")
    df = df.loc[~dup]
    if df.empty:
        raise DatasetError("No usable rows remain after validation.")

    df = df.copy()
    df["route"] = df["origin_code"] + " → " + df["destination_code"]
    df["route_label"] = (
        df["origin"] + " (" + df["origin_code"] + ") → " + df["destination"] + " (" + df["destination_code"] + ")"
    )
    df["days_to_departure"] = (df["departure_date"] - df["recorded_at"]).dt.days
    df = df.sort_values(["recorded_at", "route", "airline", "departure_date"], kind="mergesort").reset_index(drop=True)

    report = {
        "rows_read": int(rows_read),
        "rows_loaded": int(len(df)),
        "observed_after_departure_removed": int(late.sum()),
        "duplicates_removed": int(dup.sum()),
        "missing_fares": int(df["fare"].isna().sum()),
        "invalid_fares_set_to_missing": int(bad_value.sum()),
        "simulated_rows": int(df["is_simulated"].sum()),
    }
    return df, report


# --------------------------------------------------------------------------- helpers
def is_demo(df: pd.DataFrame) -> bool:
    """True when any record is flagged as simulated (drives the persistent DEMO notice)."""
    return bool(len(df)) and bool(df["is_simulated"].any())


def get_currency(df: pd.DataFrame) -> str:
    currencies = sorted(df["currency"].dropna().unique()) if len(df) else []
    if len(currencies) == 1:
        return currencies[0]
    return "mixed currencies" if currencies else "PKR"


def route_label_map(df: pd.DataFrame) -> dict[str, str]:
    return dict(df[["route", "route_label"]].drop_duplicates().itertuples(index=False, name=None))


def routes_present(df: pd.DataFrame) -> set[tuple[str, str]]:
    return set(df[["origin_code", "destination_code"]].drop_duplicates().itertuples(index=False, name=None))


def pct_change(start: Optional[float], end: Optional[float]) -> Optional[float]:
    """(end - start) / start * 100, or None if it cannot be computed reliably."""
    if start is None or end is None or pd.isna(start) or pd.isna(end) or start <= 0:
        return None
    return float((end - start) / start * 100.0)


def format_pct(value: Optional[float]) -> str:
    return "N/A" if value is None or pd.isna(value) else f"{value:+.1f}%"


def format_money(value: Optional[float], currency: str) -> str:
    return "N/A" if value is None or pd.isna(value) else f"{currency} {value:,.0f}"


def _fmt_date(ts) -> str:
    return pd.Timestamp(ts).strftime("%d %b %Y")


# --------------------------------------------------------------------------- filtering
def filter_data(
    df: pd.DataFrame,
    origins: Optional[Sequence[str]] = None,
    destinations: Optional[Sequence[str]] = None,
    routes: Optional[Sequence[str]] = None,
    airlines: Optional[Sequence[str]] = None,
    date_range: Optional[tuple] = None,
    departure_dates: Optional[Sequence] = None,
) -> pd.DataFrame:
    """Apply filters. ``None`` = do not filter; an empty list = match nothing."""
    mask = pd.Series(True, index=df.index)
    for col, values in (
        ("origin_code", origins),
        ("destination_code", destinations),
        ("route", routes),
        ("airline", airlines),
    ):
        if values is not None:
            mask &= df[col].isin(list(values))
    if date_range is not None:
        start, end = date_range
        if start is not None:
            mask &= df["recorded_at"] >= pd.Timestamp(start).normalize()
        if end is not None:
            mask &= df["recorded_at"] <= pd.Timestamp(end).normalize()
    if departure_dates is not None:
        mask &= df["departure_date"].isin([pd.Timestamp(d).normalize() for d in departure_dates])
    return df.loc[mask].copy()


# --------------------------------------------------------------------------- metrics
def matched_endpoint_change(df: pd.DataFrame) -> Optional[dict]:
    """Percentage change between the first and last observation dates of ``df``.

    Only fares that exist on BOTH endpoint dates for the same route, airline and
    departure date are compared, so a change in which fares are present cannot
    masquerade as a price movement. Returns None when that is not possible.
    """
    priced = df.dropna(subset=["fare"])
    if priced.empty:
        return None
    first, last = priced["recorded_at"].min(), priced["recorded_at"].max()
    if first == last:
        return None
    keys = ["route", "airline", "departure_date"]
    a = priced.loc[priced["recorded_at"] == first, keys + ["fare"]]
    b = priced.loc[priced["recorded_at"] == last, keys + ["fare"]]
    matched = a.merge(b, on=keys, suffixes=("_start", "_end"))
    if matched.empty:
        return None
    start_mean, end_mean = float(matched["fare_start"].mean()), float(matched["fare_end"].mean())
    pct = pct_change(start_mean, end_mean)
    if pct is None:
        return None
    return {
        "start_date": first,
        "end_date": last,
        "start_mean": start_mean,
        "end_mean": end_mean,
        "pct": pct,
        "matched": int(len(matched)),
    }


def compute_kpis(df: pd.DataFrame) -> dict:
    """KPI values for the current selection. Missing values are None, never 0."""
    kpis = {
        "routes": int(df["route"].nunique()) if len(df) else 0,
        "observations": 0,
        "min": None, "avg": None, "max": None,
        "min_info": None, "max_info": None,
        "change": None,
    }
    priced = df.dropna(subset=["fare"])
    if priced.empty:
        return kpis
    kpis["observations"] = int(len(priced))
    kpis["min"], kpis["avg"], kpis["max"] = (
        float(priced["fare"].min()), float(priced["fare"].mean()), float(priced["fare"].max()),
    )
    lo, hi = priced.loc[priced["fare"].idxmin()], priced.loc[priced["fare"].idxmax()]
    kpis["min_info"] = f"{lo['route']}, observed {_fmt_date(lo['recorded_at'])}"
    kpis["max_info"] = f"{hi['route']}, observed {_fmt_date(hi['recorded_at'])}"
    kpis["change"] = matched_endpoint_change(priced)
    return kpis


def route_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """One row per route with transparent summary statistics (numeric)."""
    rows = []
    for route, g in df.groupby("route", sort=True):
        priced = g.dropna(subset=["fare"])
        change = matched_endpoint_change(priced)
        rows.append({
            "Route": route,
            "Observations": int(len(priced)),
            "Min fare": float(priced["fare"].min()) if len(priced) else None,
            "Avg fare": float(priced["fare"].mean()) if len(priced) else None,
            "Max fare": float(priced["fare"].max()) if len(priced) else None,
            "First observation": priced["recorded_at"].min() if len(priced) else pd.NaT,
            "Last observation": priced["recorded_at"].max() if len(priced) else pd.NaT,
            "Change (matched fares)": change["pct"] if change else None,
            "Matched fares": change["matched"] if change else 0,
        })
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)


def comparison_display(table: pd.DataFrame) -> pd.DataFrame:
    """String-formatted copy of route_comparison() with 'N/A' for undefined values."""
    out = pd.DataFrame(index=table.index)
    out["Route"] = table["Route"]
    out["Observations"] = table["Observations"].astype(int)
    for col in ("Min fare", "Avg fare", "Max fare"):
        out[col] = table[col].map(lambda v: "N/A" if pd.isna(v) else f"{v:,.0f}")
    for col in ("First observation", "Last observation"):
        out[col] = table[col].map(lambda v: "N/A" if pd.isna(v) else _fmt_date(v))
    out["Change (matched fares)"] = table["Change (matched fares)"].map(format_pct)
    out["Matched fares"] = table["Matched fares"].astype(int)
    return out


def daily_route_average(df: pd.DataFrame) -> pd.DataFrame:
    """Mean fare per route per observation date (input to the comparison chart)."""
    cols = ["route", "recorded_at", "avg_fare", "quotes", "airlines", "sources"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    out = (
        df.groupby(["route", "recorded_at"], sort=True)
        .agg(
            avg_fare=("fare", "mean"),
            quotes=("fare", "count"),
            airlines=("airline", lambda s: ", ".join(sorted(s.unique()))),
            sources=("source", lambda s: "; ".join(sorted(s.unique()))),
        )
        .reset_index()
    )
    return out[cols]


def daily_airline_average(df: pd.DataFrame) -> pd.DataFrame:
    """Mean fare per route, airline and observation date (input to the detail chart)."""
    cols = ["route", "airline", "recorded_at", "avg_fare", "quotes", "sources"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    out = (
        df.groupby(["route", "airline", "recorded_at"], sort=True)
        .agg(
            avg_fare=("fare", "mean"),
            quotes=("fare", "count"),
            sources=("source", lambda s: "; ".join(sorted(s.unique()))),
        )
        .reset_index()
    )
    return out[cols]


# --------------------------------------------------------------------------- narrative
def route_summaries(df: pd.DataFrame) -> list[tuple[str, str]]:
    """Descriptive (non-predictive) summaries of observed movement, one per route."""
    results = []
    currency = get_currency(df)
    labels = route_label_map(df) if len(df) else {}
    simulated = " simulated" if len(df) and df["is_simulated"].all() else ""
    for route, g in df.groupby("route", sort=True):
        priced = g.dropna(subset=["fare"])
        label = labels.get(route, route)
        if priced.empty:
            results.append((label, "No priced observations are available for this route in the current selection."))
            continue
        lo, hi = priced.loc[priced["fare"].idxmin()], priced.loc[priced["fare"].idxmax()]
        text = (
            f"{len(priced)}{simulated} priced observations between {_fmt_date(priced['recorded_at'].min())} and "
            f"{_fmt_date(priced['recorded_at'].max())}. The lowest fare was {format_money(lo['fare'], currency)} "
            f"(observed {_fmt_date(lo['recorded_at'])}, {lo['airline']}, travel {_fmt_date(lo['departure_date'])}); "
            f"the highest was {format_money(hi['fare'], currency)} "
            f"(observed {_fmt_date(hi['recorded_at'])}, {hi['airline']}, travel {_fmt_date(hi['departure_date'])}). "
        )
        change = matched_endpoint_change(priced)
        if change:
            text += (
                f"Comparing the same {change['matched']} airline/travel-date combinations on the first and last "
                f"observation dates, the average fare moved from {format_money(change['start_mean'], currency)} to "
                f"{format_money(change['end_mean'], currency)} ({format_pct(change['pct'])}). "
            )
        else:
            text += "A reliable start-to-end change is N/A because no comparable fares exist on both endpoint dates. "
        text += "This describes past observations only and is not a forecast."
        results.append((label, text))
    return results


# --------------------------------------------------------------------------- quality & profile
def quality_warnings(df: pd.DataFrame, report: Optional[dict] = None) -> list[str]:
    """Data-quality warnings for the current selection (the DEMO notice is handled separately)."""
    warnings: list[str] = []
    if df.empty:
        return warnings
    missing = int(df["fare"].isna().sum())
    if missing:
        warnings.append(f"{missing} record(s) in this selection have no fare. They are excluded from every calculation and appear as gaps in the chart.")
    currencies = sorted(df["currency"].unique())
    if len(currencies) > 1:
        warnings.append("This selection mixes currencies (" + ", ".join(currencies) + "). Fares are not directly comparable.")
    for route, g in df.dropna(subset=["fare"]).groupby("route"):
        n_dates = g["recorded_at"].nunique()
        if n_dates < MIN_DATES_FOR_TREND:
            warnings.append(f"{route} has only {n_dates} observation date(s) in this selection, which is too few to show a reliable trend.")
    priced = int(df["fare"].notna().sum())
    if 0 < priced < SMALL_SAMPLE:
        warnings.append(f"Only {priced} priced observation(s) match your filters. Summary statistics may not be representative.")
    if report:
        if report.get("duplicates_removed"):
            warnings.append(f"{report['duplicates_removed']} duplicate record(s) were removed when the dataset was loaded.")
        if report.get("invalid_fares_set_to_missing"):
            warnings.append(f"{report['invalid_fares_set_to_missing']} invalid fare value(s) (non-numeric, zero or negative) were set to missing when the dataset was loaded.")
        if report.get("observed_after_departure_removed"):
            warnings.append(f"{report['observed_after_departure_removed']} record(s) observed after their departure date were removed when the dataset was loaded.")
    return warnings


def dataset_profile(df: pd.DataFrame) -> dict:
    """Facts about the loaded dataset for the methodology page (all computed, none hardcoded)."""
    priced = df.dropna(subset=["fare"])
    dates = pd.Series(sorted(pd.to_datetime(df["recorded_at"].unique())))
    gaps = dates.diff().dropna().dt.days
    if gaps.empty:
        frequency = "a single snapshot"
    elif gaps.nunique() == 1:
        frequency = f"one snapshot every {int(gaps.iloc[0])} day(s)"
    else:
        frequency = f"irregular intervals (median {gaps.median():g} days)"
    return {
        "records": int(len(df)),
        "priced": int(len(priced)),
        "routes": int(df["route"].nunique()),
        "observation_dates": int(len(dates)),
        "first_observation": df["recorded_at"].min(),
        "last_observation": df["recorded_at"].max(),
        "departure_dates": sorted(df["departure_date"].dt.strftime("%d %b %Y").unique()),
        "airlines": sorted(df["airline"].unique()),
        "currencies": sorted(df["currency"].unique()),
        "sources": sorted(df["source"].unique()),
        "frequency": frequency,
        "simulated_rows": int(df["is_simulated"].sum()),
    }


# --------------------------------------------------------------------------- export
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Export observations in the original CSV schema (ISO dates, blank for missing fares)."""
    out = df[REQUIRED_COLUMNS].copy()
    out["recorded_at"] = pd.to_datetime(out["recorded_at"]).dt.strftime("%Y-%m-%d")
    out["departure_date"] = pd.to_datetime(out["departure_date"]).dt.strftime("%Y-%m-%d")
    buffer = io.StringIO()
    out.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")
