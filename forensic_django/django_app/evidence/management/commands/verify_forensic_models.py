from django.core.management.base import BaseCommand

from evidence.services.detection_pipeline import get_model_health


class Command(BaseCommand):
    help = "Inspect configured forensic YOLO weights and report real loaded classes."

    def handle(self, *args, **options):
        health = get_model_health(load_classes=True)
        for item in health:
            self.stdout.write("")
            self.stdout.write(self.style.HTTP_INFO(item["model_name"]))
            self.stdout.write(f"  path: {item['path'] or '(not configured)'}")
            self.stdout.write(f"  exists: {item['path_exists']}")
            self.stdout.write(f"  enabled: {item['enabled']}")
            self.stdout.write(f"  loaded classes: {', '.join(item['loaded_classes']) or '(none)'}")
            self.stdout.write(f"  configured classes: {', '.join(item['configured_classes']) or '(none)'}")
            self.stdout.write(f"  missing classes: {', '.join(item['missing_classes']) or '(none)'}")
            self.stdout.write(f"  thresholds: {item['confidence_thresholds']}")
            self.stdout.write(f"  ready: {item['ready']}")
            self.stdout.write(f"  suitable for confirmed detection: {item['suitable_for_confirmed_detection']}")
            if item.get("load_error"):
                self.stdout.write(self.style.ERROR(f"  load error: {item['load_error']}"))

        if not any(item["ready"] for item in health):
            self.stdout.write(self.style.WARNING("No configured local forensic model is ready."))
