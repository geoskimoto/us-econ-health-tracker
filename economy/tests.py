"""
economy/tests.py

Unit, integration, model, and property tests for the economy app.
Run with: python manage.py test economy
"""
import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
from django.test import TestCase

from economy.models import DataPoint, DailyAnalysis, EconomicSeries, FetchLog


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_series(series_id="UNRATE", category="labor", invert=True) -> EconomicSeries:
    obj, _ = EconomicSeries.objects.get_or_create(
        series_id=series_id,
        defaults={
            "name": f"Test {series_id}",
            "category": category,
            "source": "fred",
            "units": "percent",
            "frequency": "monthly",
            "invert_for_score": invert,
            "is_active": True,
        },
    )
    return obj


def _make_data_points(series: EconomicSeries, count: int = 60, start_value: float = 4.0) -> None:
    base = datetime.date(2015, 1, 1)
    for i in range(count):
        d = datetime.date(base.year + i // 12, (base.month + i) % 12 + 1, 1)
        DataPoint.objects.get_or_create(series=series, date=d, defaults={"value": start_value + i * 0.01})


# ─── Model tests ──────────────────────────────────────────────────────────────

class EconomicSeriesModelTest(TestCase):
    def test_str(self):
        s = _make_series()
        self.assertIn("UNRATE", str(s))

    def test_invert_flag(self):
        s = _make_series(invert=True)
        self.assertTrue(s.invert_for_score)

    def test_is_active_default(self):
        s = _make_series()
        self.assertTrue(s.is_active)


class DataPointModelTest(TestCase):
    def test_unique_constraint(self):
        from django.db import IntegrityError
        s = _make_series()
        d = datetime.date(2024, 1, 1)
        DataPoint.objects.create(series=s, date=d, value=4.2)
        with self.assertRaises(IntegrityError):
            DataPoint.objects.create(series=s, date=d, value=4.5)

    def test_str(self):
        s = _make_series()
        dp = DataPoint.objects.create(series=s, date=datetime.date(2024, 1, 1), value=4.2)
        self.assertIn("UNRATE", str(dp))
        self.assertIn("4.2", str(dp))


class DailyAnalysisModelTest(TestCase):
    def test_composite_score_range(self):
        obj = DailyAnalysis.objects.create(
            date=datetime.date.today(),
            analysis="Test.",
            analysis_model="haiku",
            generated_at=datetime.datetime.now(tz=datetime.timezone.utc),
            composite_health_score=72.5,
            recession_probability=18.0,
        )
        self.assertGreaterEqual(obj.composite_health_score, 0)
        self.assertLessEqual(obj.composite_health_score, 100)
        self.assertGreaterEqual(obj.recession_probability, 0)
        self.assertLessEqual(obj.recession_probability, 100)

    def test_str(self):
        obj = DailyAnalysis.objects.create(
            date=datetime.date(2024, 4, 1),
            analysis="Test analysis.",
            analysis_model="haiku",
            generated_at=datetime.datetime.now(tz=datetime.timezone.utc),
        )
        self.assertIn("2024-04-01", str(obj))


# ─── Indicator unit tests ──────────────────────────────────────────────────────

class ZscoreTest(TestCase):
    def test_zscore_known_values(self):
        from economy.indicators import compute_zscore
        import numpy as np
        values = [float(i) for i in range(1, 121)]  # 120 months
        idx = pd.date_range("2014-01-01", periods=120, freq="ME")
        s = pd.Series(values, index=idx)
        z = compute_zscore(s, window_years=10)
        self.assertIsNotNone(z)
        # Latest value (120) is above mean of window, so z should be positive
        self.assertGreater(z, 0)

    def test_zscore_insufficient_data(self):
        from economy.indicators import compute_zscore
        s = pd.Series([4.0, 4.1], index=pd.date_range("2024-01-01", periods=2, freq="ME"))
        z = compute_zscore(s, window_years=10)
        self.assertIsNone(z)

    def test_zscore_zero_std(self):
        from economy.indicators import compute_zscore
        idx = pd.date_range("2014-01-01", periods=120, freq="ME")
        s = pd.Series([5.0] * 120, index=idx)
        z = compute_zscore(s, window_years=10)
        self.assertEqual(z, 0.0)


class CompositeScoreTest(TestCase):
    def test_composite_score_returns_float(self):
        """Returns 50.0 (neutral) when no data is available."""
        from economy.indicators import compute_composite_score
        score = compute_composite_score()
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)

    def test_composite_score_with_data(self):
        from economy.indicators import compute_composite_score
        s = _make_series("UNRATE", invert=True)
        _make_data_points(s, count=130, start_value=4.0)
        score = compute_composite_score()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)


class RecessionProbabilityTest(TestCase):
    def test_recession_probability_no_data(self):
        from economy.indicators import compute_recession_probability
        prob = compute_recession_probability()
        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 100.0)

    def test_recession_probability_clamped(self):
        """Score never exceeds 100 regardless of inputs."""
        from economy.indicators import compute_recession_probability
        # Add Sahm trigger data
        sahm = _make_series("SAHMREALTIME", category="labor", invert=True)
        DataPoint.objects.create(series=sahm, date=datetime.date.today(), value=0.8)
        prob = compute_recession_probability()
        self.assertLessEqual(prob, 100.0)


class YoyChangeTest(TestCase):
    def test_yoy_change_positive(self):
        from economy.indicators import get_yoy_change
        s = _make_series("RSAFS", category="consumer", invert=False)
        today = datetime.date.today()
        # Create 14 monthly points spanning 14 months back to 1 month back.
        # All must fall within the 400-day fetch window AND span at least 1 year.
        for i in range(14):
            d = today - datetime.timedelta(days=30 * (14 - i))
            DataPoint.objects.get_or_create(
                series=s, date=d, defaults={"value": 100.0 + i}
            )
        yoy = get_yoy_change("RSAFS")
        self.assertIsNotNone(yoy)
        self.assertGreater(yoy, 0)

    def test_yoy_change_insufficient_data(self):
        from economy.indicators import get_yoy_change
        yoy = get_yoy_change("MISSING_SERIES_XYZ")
        self.assertIsNone(yoy)


# ─── Fetcher unit tests ───────────────────────────────────────────────────────

class UpsertSeriesTest(TestCase):
    def test_upsert_writes_new_points(self):
        from economy.fetcher import _upsert_series
        s = _make_series("FEDFUNDS", category="macro", invert=False)
        idx = pd.date_range("2023-01-01", periods=5, freq="ME")
        data = pd.Series([5.0, 5.1, 5.2, 5.3, 5.4], index=idx)
        written = _upsert_series("FEDFUNDS", data)
        self.assertEqual(written, 5)
        self.assertEqual(DataPoint.objects.filter(series_id="FEDFUNDS").count(), 5)

    def test_upsert_skips_unknown_series(self):
        from economy.fetcher import _upsert_series
        idx = pd.date_range("2023-01-01", periods=3, freq="ME")
        data = pd.Series([1.0, 2.0, 3.0], index=idx)
        written = _upsert_series("NONEXISTENT_XYZ", data)
        self.assertEqual(written, 0)

    def test_upsert_skips_nan(self):
        from economy.fetcher import _upsert_series
        import numpy as np
        s = _make_series("GDPC1", category="macro", invert=False)
        idx = pd.date_range("2023-01-01", periods=4, freq="QE")
        data = pd.Series([21000.0, float("nan"), 21500.0, 22000.0], index=idx)
        written = _upsert_series("GDPC1", data)
        self.assertEqual(written, 3)


# ─── Integration tests ────────────────────────────────────────────────────────

class FetchDataCommandTest(TestCase):
    @patch("economy.fetcher._fred_client")
    def test_fetch_command_skips_bad_api_key(self, mock_fred):
        mock_fred.side_effect = RuntimeError("FRED_API_KEY not configured in .env")
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command("fetch_data", stdout=out)
        output = out.getvalue()
        self.assertIn("Fetch", output)

    def test_seed_series_command(self):
        from django.core.management import call_command
        from io import StringIO
        # Clear and re-seed to test idempotency
        EconomicSeries.objects.all().delete()
        out = StringIO()
        call_command("seed_series", stdout=out)
        count = EconomicSeries.objects.count()
        self.assertGreater(count, 50)
        # Second run should update, not create duplicates
        call_command("seed_series", stdout=out)
        self.assertEqual(EconomicSeries.objects.count(), count)


# ─── Analysis unit tests ──────────────────────────────────────────────────────

class AnalysisTest(TestCase):
    def test_generate_analysis_no_api_key(self):
        from economy.analysis import generate_analysis
        with self.settings(ANTHROPIC_API_KEY=""):
            result = generate_analysis()
        self.assertIsNone(result)

    def test_build_user_prompt_handles_none_values(self):
        from economy.analysis import _build_user_prompt
        snapshot = {
            "date": "2024-04-01",
            "composite_health_score": None,
            "recession_probability": None,
            "macro": {},
            "yield_curve": {},
            "labor": {},
            "housing": {},
            "markets": {},
            "consumer": {},
        }
        prompt = _build_user_prompt(snapshot)
        self.assertIn("n/a", prompt)
        self.assertNotIn("None", prompt)

    @patch("anthropic.Anthropic")
    def test_generate_analysis_saves_to_db(self, mock_anthropic_cls):
        from economy.analysis import generate_analysis
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Test analysis output.")]
        mock_msg.usage.input_tokens = 100
        mock_msg.usage.cache_read_input_tokens = 0
        mock_client.messages.create.return_value = mock_msg

        with self.settings(ANTHROPIC_API_KEY="test-key"):
            result = generate_analysis(model="claude-haiku-4-5-20251001")

        self.assertEqual(result, "Test analysis output.")
        self.assertEqual(DailyAnalysis.objects.count(), 1)
        obj = DailyAnalysis.objects.first()
        self.assertEqual(obj.analysis, "Test analysis output.")
        self.assertEqual(obj.analysis_model, "haiku")


# ─── Property tests ───────────────────────────────────────────────────────────

class PropertyTests(TestCase):
    def test_composite_score_always_in_range(self):
        from economy.indicators import compute_composite_score
        for _ in range(3):
            score = compute_composite_score()
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 100.0)

    def test_recession_probability_always_in_range(self):
        from economy.indicators import compute_recession_probability
        for _ in range(3):
            prob = compute_recession_probability()
            self.assertGreaterEqual(prob, 0.0)
            self.assertLessEqual(prob, 100.0)

    def test_zscore_clamping_in_composite(self):
        """Extreme z-scores should not push composite outside 0-100."""
        from economy.indicators import compute_composite_score
        # Add extreme low unemployment
        s = _make_series("UNRATE", invert=True)
        base = datetime.date(2010, 1, 1)
        for i in range(170):
            month = (base.month + i - 1) % 12 + 1
            year = base.year + (base.month + i - 1) // 12
            try:
                DataPoint.objects.update_or_create(
                    series=s, date=datetime.date(year, month, 1),
                    defaults={"value": max(0.1, 10.0 - i * 0.1)},
                )
            except Exception:
                pass
        score = compute_composite_score()
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)
