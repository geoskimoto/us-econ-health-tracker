"""
Management command: run_analysis
Trigger Claude Haiku (or Sonnet) daily economy analysis.
Usage:
    python manage.py run_analysis
    python manage.py run_analysis --model sonnet
"""
from django.core.management.base import BaseCommand
from economy.analysis import generate_analysis

MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}


class Command(BaseCommand):
    help = "Generate a Claude economy analysis and save it to DailyAnalysis."

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            choices=["haiku", "sonnet"],
            default="haiku",
            help="Model to use (default: haiku).",
        )

    def handle(self, *args, **options):
        model_id = MODEL_MAP[options["model"]]
        self.stdout.write(f"Running analysis with {options['model']}...")
        result = generate_analysis(model=model_id)
        if result:
            self.stdout.write(self.style.SUCCESS("Analysis complete."))
            self.stdout.write(result[:200] + "..." if len(result) > 200 else result)
        else:
            self.stdout.write(self.style.ERROR("Analysis failed — check logs."))
