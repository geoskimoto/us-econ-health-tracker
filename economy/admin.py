from django.contrib import admin
from .models import EconomicSeries, DataPoint, FetchLog, DailyAnalysis


@admin.register(EconomicSeries)
class EconomicSeriesAdmin(admin.ModelAdmin):
    list_display = ["series_id", "name", "category", "source", "frequency", "is_active"]
    list_filter = ["category", "source", "frequency", "is_active"]
    search_fields = ["series_id", "name"]


@admin.register(DataPoint)
class DataPointAdmin(admin.ModelAdmin):
    list_display = ["series_id", "date", "value"]
    list_filter = ["series__category"]
    search_fields = ["series__series_id"]
    ordering = ["-date"]


@admin.register(FetchLog)
class FetchLogAdmin(admin.ModelAdmin):
    list_display = ["started_at", "status", "series_fetched", "series_failed", "points_written"]
    list_filter = ["status"]


@admin.register(DailyAnalysis)
class DailyAnalysisAdmin(admin.ModelAdmin):
    list_display = ["date", "analysis_model", "composite_health_score", "recession_probability", "generated_at"]
    ordering = ["-date"]
