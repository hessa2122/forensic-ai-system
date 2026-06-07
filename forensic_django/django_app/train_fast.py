from ultralytics import YOLO

print("Loading model...")
model = YOLO("yolov8n.pt")

print("Starting training...")
results = model.train(
    data="datasets/merged/forensic.yaml",
    epochs=50,
    imgsz=512,
    batch=16,
    name="forensic_512",
    patience=10,
    workers=0,
    device="cpu",
    fraction=0.1,
    augment=True,
    save=True,
    verbose=True,
)

print("Done!")
print("Weights: runs/detect/forensic_512/weights/best.pt")