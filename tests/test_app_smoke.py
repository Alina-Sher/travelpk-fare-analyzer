"""End-to-end smoke test of the Streamlit UI using Streamlit's AppTest harness.

Skipped automatically when streamlit/plotly are not installed.
Run:  pytest tests/test_app_smoke.py -v     (or python -m unittest discover -s tests -v)
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HAVE_DEPS = all(importlib.util.find_spec(m) for m in ("streamlit", "plotly"))


@unittest.skipUnless(HAVE_DEPS, "streamlit/plotly not installed in this environment")
class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        from streamlit.testing.v1 import AppTest
        self.at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()

    def test_dashboard_renders_without_exception_and_shows_demo_notice(self):
        self.assertEqual(len(self.at.exception), 0)
        text = " ".join(m.value for m in self.at.markdown)
        self.assertIn("DEMO DATA — These fares are simulated", text)
        self.assertIn("Routes tracked", text)

    def test_methodology_page_renders_with_notice(self):
        self.at.sidebar.radio[0].set_value("Data Sources & Methodology").run()
        self.assertEqual(len(self.at.exception), 0)
        text = " ".join(m.value for m in self.at.markdown)
        self.assertIn("DEMO DATA — These fares are simulated", text)
        self.assertIn("data/flight_fares.csv", text)

    def test_deselecting_everything_shows_empty_state(self):
        self.at.sidebar.multiselect[0].set_value([]).run()   # origin airports -> none
        self.assertEqual(len(self.at.exception), 0)
        self.assertTrue(any("No fares match" in w.value for w in self.at.warning))


if __name__ == "__main__":
    unittest.main()
