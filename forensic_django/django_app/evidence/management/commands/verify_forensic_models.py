from django.core.management.base import BaseCommand

from evidence.services.detection_pipeline import FORENSIC_CLASSES, get_model_health


class Command(BaseCommand):
    help = "Inspect configured forensic YOLO weights and report real loaded classes."

    def handle(self, *args, **options):
        health = get_model_health(load_classes=True)
        covered = set()
        device = "cpu"
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "unknown"
        for item in health:
            if item["ready"]:
                covered.update(set(item["loaded_classes"]) & set(item["configured_classes"]))
            self.stdout.write("")
            self.stdout.write(self.style.HTTP_INFO(item["model_name"]))
            self.stdout.write(f"  path: {item['path'] or '(not configured)'}")
            self.stdout.write(f"  exists: {item['path_exists']}")
            self.stdout.write(f"  loaded: {bool(item['loaded_classes'])}")
            self.stdout.write(f"  device: {device}")
            self.stdout.write(f"  enabled: {item['enabled']}")
            self.stdout.write(f"  loaded classes: {', '.join(item['loaded_classes']) or '(none)'}")
            self.stdout.write(f"  intended classes: {', '.join(item['configured_classes']) or '(none)'}")
            self.stdout.write(f"  missing classes: {', '.join(item['missing_classes']) or '(none)'}")
            unexpected = sorted(set(item["loaded_classes"]) - set(item["configured_classes"]))
            self.stdout.write(f"  unexpected classes: {', '.join(unexpected) or '(none)'}")
            self.stdout.write(f"  thresholds: {item['confidence_thresholds']}")
            self.stdout.write(f"  ready: {item['ready']}")
            self.stdout.write(f"  suitable for confirmed detection: {item['suitable_for_confirmed_detection']}")
            if item.get("load_error"):
                self.stdout.write(self.style.ERROR(f"  load error: {item['load_error']}"))

        if not any(item["ready"] for item in health):
            self.stdout.write(self.style.WARNING("No configured local forensic model is ready."))
        missing = sorted(FORENSIC_CLASSES - covered)
        self.stdout.write("")
        self.stdout.write(f"Overall covered classes: {', '.join(sorted(covered)) or '(none)'}")
        self.stdout.write(f"Overall missing classes: {', '.join(missing) or '(none)'}")
        self.stdout.write(f"Complete six-class forensic pipeline ready: {not missing}")
