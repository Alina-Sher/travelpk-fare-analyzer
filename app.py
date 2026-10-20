"""Travel.pk Flight Price Trend Analyzer - Streamlit app.

A TechAbout task prototype. All calculations live in fare_analysis.py and all
charts in charts.py; this file only wires filters, layout and text together.
"""
from __future__ import annotations

import streamlit as st

import charts
import fare_analysis as fa
import styles

PAGE_DASHBOARD = "Dashboard"
PAGE_METHOD = "Data Sources & Methodology"

st.set_page_config(
    page_title="Travel.pk Flight Price Trend Analyzer",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)
styles.inject_css()


@st.cache_data(show_spinner="Loading fare data…")
def load_data():
    return fa.load_dataset()


try:
    DF, REPORT = load_data()
except FileNotFoundError as exc:
    st.error(f"{exc}. Add the file or restore it from the repository, then reload.")
    st.stop()
except fa.DatasetError as exc:
    st.error(f"The fare dataset failed validation: {exc} Fix {fa.DATA_FILENAME} and reload.")
    st.stop()

DEMO = fa.is_demo(DF)
CURRENCY = fa.get_currency(DF)

# ------------------------------------------------------------------ sidebar: brand + navigation
st.sidebar.markdown(styles.sidebar_brand(), unsafe_allow_html=True)
page = st.sidebar.radio("Navigate", [PAGE_DASHBOARD, PAGE_METHOD], label_visibility="collapsed")


def top_of_page(title: str, subtitle: str) -> None:
    st.markdown(styles.header(title, subtitle), unsafe_allow_html=True)
    if DEMO:  # persistent notice: shown on every page whenever any record is simulated
        st.markdown(styles.banner(fa.DEMO_NOTICE), unsafe_allow_html=True)


# ------------------------------------------------------------------ dashboard
def render_dashboard() -> None:
    top_of_page(
        "Travel.pk Flight Price Trend Analyzer",
        "See how fares on five Pakistan and UAE routes change from one observation date to the next.",
    )

    airport_names = {**dict(zip(DF["origin_code"], DF["origin"])), **dict(zip(DF["destination_code"], DF["destination"]))}
    airport_fmt = lambda code: f"{airport_names.get(code, code)} ({code})"
    route_labels = fa.route_label_map(DF)

    st.sidebar.markdown("### Filters")
    origin_opts = sorted(DF["origin_code"].unique())
    dest_opts = sorted(DF["destination_code"].unique())
    origins = st.sidebar.multiselect("Origin airport", origin_opts, default=origin_opts, format_func=airport_fmt,
                                     help="Departure airports to include. Deselect all to see the empty state.")
    dests = st.sidebar.multiselect("Destination airport", dest_opts, default=dest_opts, format_func=airport_fmt,
                                   help="Arrival airports to include.")
    available = DF[DF["origin_code"].isin(origins) & DF["destination_code"].isin(dests)]
    route_opts = sorted(available["route"].unique())
    routes = st.sidebar.multiselect("Route", route_opts, default=route_opts, format_func=lambda r: route_labels[r],
                                    help="Only routes that match the airports selected above are listed.")
    airline_opts = sorted(DF["airline"].unique())
    airlines = st.sidebar.multiselect(
        "Airline", airline_opts, default=airline_opts,
        help="Carrier names in the demo dataset are placeholders, not real airlines." if DEMO else "Carriers to include.")

    min_d, max_d = DF["recorded_at"].min().date(), DF["recorded_at"].max().date()
    picked = st.sidebar.date_input("Observation date range", value=(min_d, max_d), min_value=min_d, max_value=max_d,
                                   help="The dates on which fares were recorded (not the travel dates).")
    if isinstance(picked, (tuple, list)) and len(picked) == 2:
        start, end = picked
    else:
        start, end = min_d, max_d
        st.sidebar.info("Pick an end date to apply the range. Showing the full range for now.")

    dep_opts = sorted(DF["departure_date"].dt.date.unique())
    deps = st.sidebar.multiselect("Travel (departure) date", dep_opts, default=dep_opts,
                                  format_func=lambda d: d.strftime("%d %b %Y"),
                                  help="The flight date each fare was quoted for.")
    st.sidebar.markdown(
        '<div class="tp-side-note">TechAbout task prototype for Travel.pk. '
        "Not an official Travel.pk product or endorsement.</div>", unsafe_allow_html=True)

    filtered = fa.filter_data(DF, origins=origins, destinations=dests, routes=routes, airlines=airlines,
                              date_range=(start, end), departure_dates=deps)

    if filtered.empty:
        st.warning(
            "No fares match the current filters. Widen the observation date range, or select at least one "
            "origin, destination, route, airline and travel date in the sidebar."
        )
        return

    for message in fa.quality_warnings(filtered, REPORT):
        st.warning(message, icon="⚠️")

    # ---- KPI cards (every value computed from the filtered data)
    k = fa.compute_kpis(filtered)
    change = k["change"]
    cards = [
        ("Routes tracked", f"{k['routes']}", "in the current selection", "Distinct origin → destination routes after filtering."),
        ("Fare observations", f"{k['observations']:,}", "priced records", "Rows with a valid fare. Records with a missing fare are excluded."),
        ("Lowest observed fare", fa.format_money(k["min"], CURRENCY), k["min_info"] or "", "Smallest single fare in the selection."),
        ("Average fare", fa.format_money(k["avg"], CURRENCY), "mean of all priced records", "Simple mean of every priced record in the selection (routes with different base fares are pooled)."),
        ("Highest observed fare", fa.format_money(k["max"], CURRENCY), k["max_info"] or "", "Largest single fare in the selection."),
        ("Change over period", fa.format_pct(change["pct"]) if change else "N/A",
         (f"{change['start_date']:%d %b} to {change['end_date']:%d %b %Y}, {change['matched']} matched fares" if change
          else "needs 2+ observation dates with matching fares"),
         "Average of matching fares (same route, airline and travel date) on the last observation date versus the first."),
    ]
    st.markdown(styles.kpi_grid(cards), unsafe_allow_html=True)

    # ---- trend chart
    st.subheader("Historical fare trend")
    view = st.radio("Chart view", ["Compare routes", "One route by airline"], horizontal=True,
                    help="Compare routes: one line per route (average of selected fares). "
                         "One route by airline: one line per airline for a single route.")
    if view == "Compare routes":
        fig = charts.build_trend_chart(filtered, mode="routes", currency=CURRENCY)
        st.caption("Each point is the average fare across the selected airlines and travel dates recorded on that date.")
    else:
        present = sorted(filtered["route"].unique())
        chosen = st.selectbox("Route", present, format_func=lambda r: route_labels[r])
        fig = charts.build_trend_chart(filtered[filtered["route"] == chosen], mode="airlines", currency=CURRENCY)
        st.caption("Each point is that airline's average fare across the selected travel dates on that observation date.")
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

    # ---- route comparison
    st.subheader("Route comparison")
    table = fa.route_comparison(filtered)
    st.dataframe(fa.comparison_display(table), use_container_width=True, hide_index=True)
    st.caption(
        f"Fares in {CURRENCY}. Reflects the current filters; reset them to see all five routes. "
        "Change compares the same airline and travel date on a route's first and last observation date; "
        "N/A means no such matched fares exist."
    )

    # ---- route summaries
    st.subheader("What the data shows")
    st.caption("Descriptions of past observations only. They do not predict future fares.")
    for label, text in fa.route_summaries(filtered):
        st.markdown(f'<span class="route-name">{label}</span><br>{text}', unsafe_allow_html=True)

    # ---- data + download
    st.subheader("Underlying data")
    st.download_button(
        "Download filtered observations (CSV)", data=fa.to_csv_bytes(filtered),
        file_name="travelpk_filtered_fares.csv", mime="text/csv",
        help="Exports exactly the rows behind the charts and metrics above.")
    with st.expander(f"View {len(filtered):,} filtered records"):
        view_df = filtered[fa.REQUIRED_COLUMNS].copy()
        view_df["recorded_at"] = view_df["recorded_at"].dt.date
        view_df["departure_date"] = view_df["departure_date"].dt.date
        st.dataframe(view_df, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------ methodology
def render_methodology() -> None:
    top_of_page("Data Sources & Methodology",
                "Where the numbers come from, how they are cleaned and how every metric is calculated.")
    p = fa.dataset_profile(DF)
    fmt = lambda t: t.strftime("%d %b %Y")
    all_simulated = p["simulated_rows"] == p["records"]

    st.subheader("Source")
    st.markdown(f"- **Dataset file:** `{fa.DATA_FILENAME}` (read by `fare_analysis.load_dataset`).")
    if all_simulated:
        st.markdown(
            "- **Real or simulated:** **Simulated.** Every record has `is_simulated = True`. The fares were produced "
            "by `scripts/generate_sample_data.py` (a seeded random booking-curve model) to demonstrate the application. "
            "They are **not** real airline prices, were not collected from any airline or travel website, and must "
            "not be used for pricing or purchasing decisions.\n"
            "- **Genuine archived observations?** No. The historical records are demonstration data. The airline "
            "names (`Simulated Carrier A/B/C`) are placeholders, not real carriers.")
    elif p["simulated_rows"] == 0:
        st.markdown("- **Real or simulated:** every record is flagged `is_simulated = False`. Provenance is given "
                    "per record in the `source` column (listed below). Verify it before relying on the data.")
    else:
        st.markdown(f"- **Real or simulated:** mixed. {p['simulated_rows']:,} of {p['records']:,} records are "
                    "simulated. Filter on the `is_simulated` column in the CSV before drawing conclusions.")
    st.markdown("- **`source` values:** " + "; ".join(f"`{s}`" for s in p["sources"]))
    st.markdown("- **Live API:** **None.** The app reads only the CSV above. No airline or travel API is called, "
                "and no credentials are used.")

    st.subheader("Coverage")
    st.markdown(
        f"- **Collection period:** {fmt(p['first_observation'])} to {fmt(p['last_observation'])} "
        f"({p['observation_dates']} observation dates).\n"
        f"- **Frequency:** {p['frequency']}.\n"
        f"- **Size:** {p['records']:,} records ({p['priced']:,} with a fare) across {p['routes']} routes.\n"
        f"- **Travel dates quoted:** {', '.join(p['departure_dates'])}.\n"
        f"- **Airlines:** {', '.join(p['airlines'])}.")
    st.dataframe(fa.comparison_display(fa.route_comparison(DF)), use_container_width=True, hide_index=True)

    st.subheader("Currency and fare definition")
    st.markdown(
        f"- **Currency:** {', '.join(p['currencies'])}. All fares in one chart or metric use the same currency.\n"
        "- **Fare:** one record is the lowest one-way economy fare for one airline on one route and one travel date, "
        "as seen on one observation date (`recorded_at`). Taxes and fees are treated as included. Fares are "
        "stored as whole currency units.\n"
        "- **Observation date vs travel date:** charts plot `recorded_at`; `departure_date` is the flight date.")

    st.subheader("Cleaning and validation")
    st.markdown(
        f"On load the app checks and reports the following (counts for this file):\n\n"
        f"- All 11 required columns must exist; otherwise loading stops with an error.\n"
        f"- `recorded_at` and `departure_date` must be valid `YYYY-MM-DD` dates; otherwise loading stops.\n"
        f"- Whitespace is trimmed, airport codes and currency are upper-cased, `is_simulated` must be true/false.\n"
        f"- Non-numeric, zero or negative fares are set to missing: **{REPORT['invalid_fares_set_to_missing']}** found.\n"
        f"- Records observed after their departure date are removed: **{REPORT['observed_after_departure_removed']}** found.\n"
        f"- Duplicates (same observation date, route, airline and travel date) are removed: **{REPORT['duplicates_removed']}** found.\n"
        f"- Blank fares are kept but excluded from calculations and shown as chart gaps: **{REPORT['missing_fares']}** present.\n"
        f"- Rows are sorted chronologically by `recorded_at`.\n"
        f"- {REPORT['rows_read']:,} rows read, {REPORT['rows_loaded']:,} rows loaded.")

    st.subheader("How metrics are calculated")
    st.markdown(
        "All metrics use only records that match the current filters and have a fare.\n\n"
        "- **Minimum / maximum:** smallest / largest single fare.\n"
        "- **Average:** arithmetic mean of all fares (sum ÷ count). Pooling routes with different base fares means "
        "the overall average mostly describes the mix of routes; use the per-route table to compare routes.\n"
        "- **Chart points:** the mean of the selected fares recorded on that date (per route, or per airline and route).\n"
        "- **Percentage change:** take the route's (or selection's) first and last observation dates. Keep only fares "
        "present on both dates for the same route, airline and travel date. Then "
        "`(mean on last date − mean on first date) ÷ mean on first date × 100`. If the two dates are the same, no fares "
        "match, or the starting mean is not positive, the result is shown as **N/A**.")

    st.subheader("Known limitations")
    st.markdown(
        "- The data is simulated, so its movements reflect a generic model (fares tend to rise as departure nears, "
        "plus noise and one built-in promotional dip on LHE → ISB), not real market behaviour.\n"
        "- Observations are every few days, not continuous, and each route has few airlines and travel dates.\n"
        "- Fares are for one-way economy only; baggage, seat and payment fees are not modelled.\n"
        "- Historical patterns do not establish future price movements, and this app makes no forecasts.\n"
        "- Replacing the CSV with real data needs a source you are entitled to use; see the README.")


if page == PAGE_DASHBOARD:
    render_dashboard()
else:
    render_methodology()
