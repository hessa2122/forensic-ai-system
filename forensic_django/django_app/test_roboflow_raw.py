import os
from PIL import Image
from inference_sdk import InferenceHTTPClient

image_path = r"C:\Users\Dell\Downloads\gun.jpg"

print("API key found:", bool(os.environ.get("ROBOFLOW_API_KEY")))

img = Image.open(image_path).convert("RGB")
print("Image loaded:", img.size, img.mode)

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=os.environ.get("ROBOFLOW_API_KEY")
)

model_ids = [
    "evidence-detection-l2tem/1",
    "bloodstain-z2fox/1",
]

for model_id in model_ids:
    print("\nMODEL:", model_id)
    result = client.infer(img, model_id=model_id)
    print(result)