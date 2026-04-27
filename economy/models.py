from django.db import models


class EconomicSeries(models.Model):
    CATEGORY_CHOICES = [
        ("macro", "Macro"),
        ("labor", "Labor"),
        ("housing", "Housing"),
        ("markets", "Markets"),
        ("consumer", "Consumer & Business"),
    ]
    SOURCE_CHOICES = [
        ("fred", "FRED"),
        ("yfinance", "yfinance"),
    ]
    FREQUENCY_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
    ]

    series_id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="fred")
    units = models.CharField(max_length=100, blank=True)
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default="monthly")
    is_active = models.BooleanField(default=True)
    invert_for_score = models.BooleanField(
        default=False,
        help_text="True for series where high values are bad (unemployment, claims, VIX).",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "series_id"]
        verbose_name_plural = "Economic Series"

    def __str__(self):
        return f"{self.series_id} — {self.name}"


class DataPoint(models.Model):
    series = models.ForeignKey(
        EconomicSeries, on_delete=models.CASCADE, related_name="data_points"
    )
    date = models.DateField()
    value = models.FloatField()

    class Meta:
        unique_together = ("series", "date")
        ordering = ["series", "date"]
        indexes = [
            models.Index(fields=["series", "date"]),
        ]

    def __str__(self):
        return f"{self.series_id} @ {self.date}: {self.value}"


class FetchLog(models.Model):
    STATUS_CHOICES = [
        ("success", "Success"),
        ("partial", "Partial"),
        ("failed", "Failed"),
    ]

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="failed")
    series_fetched = models.IntegerField(default=0)
    series_failed = models.IntegerField(default=0)
    points_written = models.IntegerField(default=0)
    error_detail = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Fetch {self.started_at:%Y-%m-%d %H:%M} — {self.status}"


class DailyAnalysis(models.Model):
    date = models.DateField(unique=True)
    analysis = models.TextField()
    analysis_model = models.CharField(max_length=30)
    generated_at = models.DateTimeField()
    snapshot_json = models.JSONField(
        default=dict,
        help_text="Serialized indicator snapshot sent to the model.",
    )
    recession_probability = models.FloatField(
        null=True, blank=True, help_text="0–100 score."
    )
    composite_health_score = models.FloatField(
        null=True, blank=True, help_text="0–100 score."
    )

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Daily Analyses"

    def __str__(self):
        return f"Analysis {self.date} ({self.analysis_model})"
