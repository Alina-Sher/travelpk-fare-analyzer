"""Automated tests for data loading, validation and calculations.

Run with either:  python -m unittest discover -s tests -v   |   pytest -v
"""
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fare_analysis as fa  # noqa: E402


def write_csv(rows, columns=None) -> Path:
    """Write rows (list of dicts) to a temp CSV and return its path."""
    path = Path(tempfile.mkdtemp()) / "fares.csv"
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
    return path


def row(rec="2026-01-01", route=("LHE", "KHI"), airline="A", dep="2026-02-01", fare=100, sim=True):
    names = {"LHE": "Lahore", "KHI": "Karachi", "ISB": "Islamabad", "DXB": "Dubai"}
    return {"recorded_at": rec, "origin": names[route[0]], "origin_code": route[0],
            "destination": names[route[1]], "destination_code": route[1], "airline": airline,
            "departure_date": dep, "fare": fare, "currency": "PKR", "source": "unit test", "is_simulated": sim}


class RealDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df, cls.report = fa.load_dataset()

    def test_loads_dataset(self):
        self.assertTrue(fa.DATA_PATH.exists())
        self.assertGreater(len(self.df), 0)
        self.assertEqual(self.report["rows_loaded"], len(self.df))

    def test_required_columns_present_in_csv(self):
        raw = pd.read_csv(fa.DATA_PATH, nrows=1)
        for col in fa.REQUIRED_COLUMNS:
            self.assertIn(col, raw.columns)

    def test_at_least_five_required_routes_present(self):
        present = fa.routes_present(self.df)
        for r in fa.REQUIRED_ROUTES:
            self.assertIn(r, present)
        self.assertGreaterEqual(self.df["route"].nunique(), 5)

    def test_multiple_observations_per_route(self):
        for route, g in self.df.groupby("route"):
            self.assertGreaterEqual(g["recorded_at"].nunique(), fa.MIN_DATES_FOR_TREND, route)
            self.assertGreaterEqual(g["fare"].notna().sum(), 20, route)

    def test_fare_values_valid(self):
        fares = self.df["fare"].dropna()
        self.assertTrue((fares > 0).all())
        self.assertTrue(fares.map(lambda v: v == v and abs(v) != float("inf")).all())
        self.assertEqual(set(self.df["currency"]), {"PKR"})

    def test_dates_parsed_and_sorted(self):
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(self.df["recorded_at"]))
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(self.df["departure_date"]))
        self.assertTrue(self.df["recorded_at"].is_monotonic_increasing)
        self.assertTrue((self.df["recorded_at"] <= self.df["departure_date"]).all())

    def test_kpis_match_independent_pandas_calculation(self):
        k = fa.compute_kpis(self.df)
        fares = self.df["fare"].dropna()
        self.assertEqual(k["observations"], len(fares))
        self.assertEqual(k["min"], fares.min())
        self.assertEqual(k["max"], fares.max())
        self.assertAlmostEqual(k["avg"], fares.mean())
        self.assertEqual(k["routes"], 5)

    def test_kpis_follow_filters(self):
        sub = fa.filter_data(self.df, routes=["LHE → DXB"])
        k = fa.compute_kpis(sub)
        self.assertEqual(k["routes"], 1)
        self.assertEqual(k["min"], sub["fare"].min())
        self.assertGreater(k["avg"], fa.compute_kpis(fa.filter_data(self.df, routes=["LHE → ISB"]))["avg"])

    def test_filters(self):
        self.assertEqual(set(fa.filter_data(self.df, origins=["ISB"])["origin_code"]), {"ISB"})
        self.assertEqual(set(fa.filter_data(self.df, destinations=["DXB"])["route"]), {"LHE → DXB", "ISB → DXB"})
        self.assertEqual(set(fa.filter_data(self.df, airlines=["Simulated Carrier B"])["airline"]), {"Simulated Carrier B"})
        dr = fa.filter_data(self.df, date_range=("2026-08-01", "2026-08-31"))
        self.assertTrue(dr["recorded_at"].between("2026-08-01", "2026-08-31").all())
        dep = fa.filter_data(self.df, departure_dates=["2026-11-15"])
        self.assertEqual(set(dep["departure_date"]), {pd.Timestamp("2026-11-15")})
        self.assertEqual(len(fa.filter_data(self.df)), len(self.df))  # no filters = everything

    def test_empty_filters_return_empty_and_do_not_crash(self):
        for kwargs in ({"routes": []}, {"airlines": []}, {"origins": []}, {"departure_dates": []},
                       {"date_range": ("2030-01-01", "2030-02-01")}):
            empty = fa.filter_data(self.df, **kwargs)
            self.assertTrue(empty.empty, kwargs)
            k = fa.compute_kpis(empty)
            self.assertEqual((k["routes"], k["observations"]), (0, 0))
            self.assertIsNone(k["min"]); self.assertIsNone(k["avg"]); self.assertIsNone(k["change"])
            self.assertTrue(fa.route_comparison(empty).empty)
            self.assertEqual(list(fa.route_comparison(empty).columns), fa.COMPARISON_COLUMNS)
            self.assertEqual(fa.route_summaries(empty), [])
            self.assertEqual(fa.quality_warnings(empty), [])
            self.assertTrue(fa.daily_route_average(empty).empty)
            self.assertTrue(fa.daily_airline_average(empty).empty)

    def test_csv_export_roundtrip(self):
        sub = fa.filter_data(self.df, routes=["LHE → KHI"], date_range=("2026-08-01", "2026-09-01"))
        data = fa.to_csv_bytes(sub)
        self.assertIsInstance(data, bytes)
        exported = pd.read_csv(io.BytesIO(data))
        self.assertEqual(list(exported.columns), fa.REQUIRED_COLUMNS)
        self.assertEqual(len(exported), len(sub))
        path = Path(tempfile.mkdtemp()) / "export.csv"
        path.write_bytes(data)
        reloaded, _ = fa.load_dataset(path)
        self.assertEqual(len(reloaded), len(sub))
        self.assertAlmostEqual(reloaded["fare"].sum(), sub["fare"].sum())

    def test_simulated_data_is_labelled(self):
        self.assertTrue(self.df["is_simulated"].all())
        self.assertEqual(self.report["simulated_rows"], len(self.df))
        self.assertTrue(fa.is_demo(self.df))
        self.assertTrue(self.df["source"].str.startswith("Simulated").all())
        self.assertTrue(self.df["airline"].str.startswith("Simulated").all())  # no real airline attribution
        self.assertEqual(fa.DEMO_NOTICE,
                         "DEMO DATA — These fares are simulated for demonstration and are not live airline prices.")
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("fa.DEMO_NOTICE", app_source)       # banner is rendered by the UI...
        self.assertIn("styles.banner", app_source)        # ...on every page via top_of_page()

    def test_comparison_table_covers_all_routes(self):
        table = fa.route_comparison(self.df)
        self.assertEqual(len(table), 5)
        self.assertTrue((table["Min fare"] <= table["Avg fare"]).all())
        self.assertTrue((table["Avg fare"] <= table["Max fare"]).all())
        display = fa.comparison_display(table)
        self.assertEqual(list(display.columns), fa.COMPARISON_COLUMNS)

    def test_summaries_make_no_predictions(self):
        for _, text in fa.route_summaries(self.df):
            self.assertIn("not a forecast", text)
            for banned in ("will rise", "will fall", "will increase", "will drop", "expected to"):
                self.assertNotIn(banned, text.lower())


class CalculationTests(unittest.TestCase):
    def test_pct_change(self):
        self.assertAlmostEqual(fa.pct_change(100, 125), 25.0)
        self.assertAlmostEqual(fa.pct_change(200, 150), -25.0)
        self.assertEqual(fa.pct_change(100, 100), 0.0)
        self.assertIsNone(fa.pct_change(0, 50))
        self.assertIsNone(fa.pct_change(-5, 50))
        self.assertIsNone(fa.pct_change(None, 50))
        self.assertIsNone(fa.pct_change(50, float("nan")))
        self.assertEqual(fa.format_pct(None), "N/A")
        self.assertEqual(fa.format_pct(12.345), "+12.3%")

    def test_min_max_avg_known_values(self):
        path = write_csv([row(rec="2026-01-01", fare=100), row(rec="2026-01-02", fare=200), row(rec="2026-01-03", fare=300),
                          row(rec="2026-01-04", fare="")])
        df, report = fa.load_dataset(path)
        k = fa.compute_kpis(df)
        self.assertEqual((k["min"], k["max"], k["observations"]), (100, 300, 3))
        self.assertAlmostEqual(k["avg"], 200.0)
        self.assertEqual(report["missing_fares"], 1)

    def test_change_uses_matched_fares_only(self):
        rows = [
            row(rec="2026-01-01", airline="A", fare=100), row(rec="2026-01-01", airline="B", fare=300),
            row(rec="2026-01-10", airline="A", fare=150),   # B has no fare on the last date -> not matched
            row(rec="2026-01-10", airline="C", fare=9999),  # C has no fare on the first date -> not matched
        ]
        df, _ = fa.load_dataset(write_csv(rows))
        change = fa.compute_kpis(df)["change"]
        self.assertEqual(change["matched"], 1)
        self.assertAlmostEqual(change["pct"], 50.0)  # 100 -> 150, nothing else

    def test_change_is_na_when_not_calculable(self):
        single_date, _ = fa.load_dataset(write_csv([row(fare=100), row(airline="B", fare=120)]))
        self.assertIsNone(fa.compute_kpis(single_date)["change"])
        no_match, _ = fa.load_dataset(write_csv([row(rec="2026-01-01", airline="A"), row(rec="2026-01-05", airline="B")]))
        self.assertIsNone(fa.compute_kpis(no_match)["change"])
        table = fa.comparison_display(fa.route_comparison(no_match))
        self.assertEqual(table.loc[0, "Change (matched fares)"], "N/A")

    def test_chronological_sorting_of_shuffled_input(self):
        rows = [row(rec="2026-03-01", dep="2026-06-01", fare=3), row(rec="2026-01-01", dep="2026-06-01", fare=1),
                row(rec="2026-02-01", dep="2026-06-01", fare=2)]
        df, _ = fa.load_dataset(write_csv(rows))
        self.assertEqual(list(df["fare"]), [1, 2, 3])
        series = fa.daily_route_average(df)
        self.assertTrue(series["recorded_at"].is_monotonic_increasing)

    def test_cleaning_rules(self):
        rows = [row(fare=100), row(fare=100),                      # duplicate
                row(rec="2026-01-02", fare=-5),                    # negative -> missing
                row(rec="2026-01-03", fare="abc"),                 # non-numeric -> missing
                row(rec="2026-03-01", dep="2026-02-01", fare=50)]  # observed after departure -> removed
        df, rep = fa.load_dataset(write_csv(rows))
        self.assertEqual(rep["duplicates_removed"], 1)
        self.assertEqual(rep["invalid_fares_set_to_missing"], 2)
        self.assertEqual(rep["observed_after_departure_removed"], 1)
        self.assertEqual(len(df), 3)
        self.assertEqual(int(df["fare"].isna().sum()), 2)
        self.assertTrue(any("invalid fare" in w for w in fa.quality_warnings(df, rep)))

    def test_bad_input_raises(self):
        with self.assertRaises(fa.DatasetError):
            fa.load_dataset(write_csv([row()], columns=[c for c in fa.REQUIRED_COLUMNS if c != "airline"] ))
        with self.assertRaises(fa.DatasetError):
            fa.load_dataset(write_csv([row(rec="31/12/2026")]))
        with self.assertRaises(fa.DatasetError):
            fa.load_dataset(write_csv([row(sim="maybe")]))
        with self.assertRaises(FileNotFoundError):
            fa.load_dataset(ROOT / "data" / "does_not_exist.csv")

    def test_real_data_flag_disables_demo_notice(self):
        df, _ = fa.load_dataset(write_csv([row(sim=False)]))
        self.assertFalse(fa.is_demo(df))

    def test_sparse_route_triggers_quality_warning(self):
        df, rep = fa.load_dataset(write_csv([row(rec="2026-01-01"), row(rec="2026-01-02")]))
        self.assertTrue(any("too few" in w for w in fa.quality_warnings(df, rep)))


@unittest.skipUnless(importlib.util.find_spec("plotly"), "plotly not installed in this environment")
class ChartTests(unittest.TestCase):
    def test_chart_has_one_dated_trace_per_route(self):
        import charts
        df, _ = fa.load_dataset()
        fig = charts.build_trend_chart(df, mode="routes")
        self.assertEqual(len(fig.data), 5)
        for trace in fig.data:
            self.assertGreaterEqual(len(trace.x), fa.MIN_DATES_FOR_TREND)
            self.assertTrue(pd.Series(pd.to_datetime(list(trace.x))).is_monotonic_increasing)
        detail = charts.build_trend_chart(df[df["route"] == "LHE → KHI"], mode="airlines")
        self.assertEqual(len(detail.data), 3)


if __name__ == "__main__":
    unittest.main()
