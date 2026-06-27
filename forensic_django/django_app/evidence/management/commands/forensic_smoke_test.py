from django.core.management.base import BaseCommand, CommandError

from evidence.model_registry import get_enabled_model_metadata


class Command(BaseCommand):
    help = "Validate local forensic model files, class metadata, and registry schema."

    def handle(self, *args, **options):
        metadata = get_enabled_model_metadata()
        failures = []
        for item in metadata:
            self.stdout.write(
                f"{item['model_name']} {item['model_version']} "
                f"enabled={item['enabled']} exists={item['path_exists']} "
                f"classes={','.join(item.get('loaded_classes', []))}"
            )
            if item["enabled"] and not item["path_exists"]:
                failures.append(f"Missing enabled model: {item['model_version']}")
            if item["enabled"] and item.get("load_error"):
                failures.append(f"Could not load {item['model_version']}: {item['load_error']}")
        if failures:
            raise CommandError("; ".join(failures))
        self.stdout.write(self.style.SUCCESS("Forensic model registry smoke test passed."))
