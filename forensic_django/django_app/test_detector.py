import os
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_detector.py <image_path>")
        return 2

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print(f"Image not found: {image_path}")
        return 2

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "forensic_project.settings")
    import django

    django.setup()

    from evidence.ai_detector import analyze_image

    result = analyze_image(str(image_path))
    print("Detections:", len(result["detections"]))
    for detection in result["detections"]:
        print(
            f"  [{detection.get('source')}] {detection.get('label')} "
            f"- {float(detection.get('confidence', 0)) * 100:.0f}%"
        )
    print("Summary:", result.get("scene_summary", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
