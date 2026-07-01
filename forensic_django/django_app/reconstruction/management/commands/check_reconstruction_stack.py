from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check local 3D reconstruction dependencies and writable output directories."

    def _check_import(self, module_name):
        try:
            module = __import__(module_name)
            return True, getattr(module, "__version__", "unknown")
        except Exception as exc:
            return False, str(exc)

    def handle(self, *args, **options):
        checks = []
        for module_name in ("open3d", "trimesh", "torch", "transformers"):
            ok, detail = self._check_import(module_name)
            checks.append((module_name, ok, detail))

        torch_ok, _ = self._check_import("torch")
        if torch_ok:
            import torch

            checks.append(("CUDA available", bool(torch.cuda.is_available()), str(torch.cuda.is_available())))
        else:
            checks.append(("CUDA available", False, "torch unavailable"))

        for rel in ("scenes/pointclouds", "scenes/depthmaps"):
            path = Path(settings.MEDIA_ROOT) / rel
            try:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / ".write_check"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
                checks.append((f"writable {rel}", True, str(path)))
            except Exception as exc:
                checks.append((f"writable {rel}", False, str(exc)))

        all_ok = True
        for name, ok, detail in checks:
            all_ok = all_ok and ok
            style = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(style(f"{name}: {'OK' if ok else 'FAILED'} ({detail})"))

        if not all_ok:
            self.stdout.write(self.style.WARNING("Reconstruction stack is not fully ready. Strict mode will fail clearly."))
