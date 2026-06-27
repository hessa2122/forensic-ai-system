import os
import sys
from pathlib import Path

from PIL import Image


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_roboflow_raw.py <image_path>")
        return 2

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print(f"Image not found: {image_path}")
        return 2

    try:
        from inference_sdk import InferenceHTTPClient
    except ImportError:
        print("inference_sdk is not installed.")
        return 2

    api_key = os.environ.get("ROBOFLOW_API_KEY")
    print("API key found:", bool(api_key))
    if not api_key:
        return 2

    img = Image.open(image_path).convert("RGB")
    print("Image loaded:", img.size, img.mode)

    client = InferenceHTTPClient(
        api_url="https://serverless.roboflow.com",
        api_key=api_key,
    )

    for model_id in ["evidence-detection-l2tem/1", "bloodstain-z2fox/1"]:
        print("\nMODEL:", model_id)
        print(client.infer(str(image_path), model_id=model_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
