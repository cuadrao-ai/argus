"""Data-contract checks independent of any platform or financial engine."""
import datetime as dt
import json
import math
import unittest
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/series.json"


def validate(bundle):
    assert bundle["schema_version"] == "argus.chart-prototype/v1"
    assert bundle["synthetic"] is True
    assert bundle["date_semantics"] == "civil-date-utc"
    ids = set()
    for case in bundle["cases"]:
        assert case["id"] not in ids
        ids.add(case["id"])
        assert set(case["title"]) == {"en", "es-419"}
        assert all(case["title"].values())
        assert case["currency"] in {"USD", "DOP"}
        assert case["unit"] == "major-currency"
        previous = None
        for point in case["points"]:
            assert set(point) == {"time", "actual", "projected", "contribution"}
            date = dt.date.fromisoformat(point["time"])
            assert date.isoformat() == point["time"]
            assert previous is None or previous < date
            previous = date
            for key in ("actual", "projected", "contribution"):
                value = point[key]
                assert value is None or (
                    type(value) in {int, float} and math.isfinite(value)
                    and abs(value * 100 - round(value * 100)) < 1e-7
                )
            assert point["contribution"] is None or point["contribution"] >= 0


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads(FIXTURE.read_text())

    def test_all_platforms_receive_well_defined_dates_units_and_values(self):
        validate(self.bundle)

    def test_matrix_covers_edge_cases_and_strategy_shapes(self):
        cases = self.bundle["cases"]
        self.assertTrue(any(not c["points"] for c in cases))
        self.assertTrue(any(len(c["points"]) == 1 for c in cases))
        self.assertTrue(any(len(c["points"]) >= 2000 for c in cases))
        self.assertTrue({"buy-and-hold", "dca-accumulation"} <= {c["shape"] for c in cases})
        self.assertEqual({c["currency"] for c in cases}, {"USD", "DOP"})
        points = [p for c in cases for p in c["points"]]
        self.assertTrue(any(p["actual"] == 0 for p in points))
        self.assertTrue(any(p["actual"] is not None and p["actual"] < 0 for p in points))
        self.assertTrue(any(p["actual"] is None and p["projected"] is None for p in points))
        self.assertTrue(any(p["actual"] is not None and p["projected"] is not None for p in points))
        self.assertTrue(any(
            a["actual"] is not None and a["actual"] == b["actual"]
            for c in cases for a, b in zip(c["points"], c["points"][1:])
        ))

    def test_contribution_jump_is_nominal_value_not_a_return(self):
        recurring = next(c for c in self.bundle["cases"] if c["shape"] == "dca-accumulation")
        deposits = [p for p in recurring["points"] if p["contribution"] is not None]
        self.assertGreaterEqual(len(deposits), 3)
        funding = recurring["funding"]
        self.assertEqual(deposits[0]["contribution"], funding["starting_capital"])
        self.assertEqual(funding["cadence"], "weekly")
        for earlier, later in zip(deposits, deposits[1:]):
            self.assertEqual(later["contribution"], funding["recurring_contribution"])
            self.assertEqual(
                (dt.date.fromisoformat(later["time"]) - dt.date.fromisoformat(earlier["time"])).days,
                7,
            )
        self.assertTrue(any(
            b["contribution"] is not None and a["actual"] is not None
            and b["actual"] - a["actual"] == b["contribution"]
            for a, b in zip(recurring["points"], recurring["points"][1:])
        ))

    def test_shared_series_colors_remain_visible_on_both_surfaces(self):
        style = json.loads(FIXTURE.with_name("visual-style.json").read_text())

        def luminance(color):
            channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

        for theme, background in (("light", "#ffffff"), ("dark", "#191c1f")):
            for series, color in style[theme].items():
                with self.subTest(theme=theme, series=series):
                    values = sorted((luminance(color), luminance(background)))
                    self.assertGreaterEqual((values[1] + 0.05) / (values[0] + 0.05), 3)

    def test_ambiguous_or_invalid_facts_are_rejected(self):
        for invalid in (True, float("nan"), float("inf"), "100", 1.001):
            with self.subTest(invalid=invalid):
                altered = json.loads(FIXTURE.read_text())
                altered["cases"][0]["points"][0]["actual"] = invalid
                with self.assertRaises(AssertionError):
                    validate(altered)
        altered = json.loads(FIXTURE.read_text())
        altered["cases"][0]["points"].reverse()
        with self.assertRaises(AssertionError):
            validate(altered)


if __name__ == "__main__":
    unittest.main()
