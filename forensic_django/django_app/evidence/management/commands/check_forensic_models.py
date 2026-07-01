from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Inspect configured forensic YOLO weights and report real loaded classes."

    def handle(self, *args, **options):
        call_command("verify_forensic_models")
