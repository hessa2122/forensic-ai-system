from ultralytics import YOLO

print("Loading YOLOv8 model...")
model = YOLO("yolov8n.pt")  # nano = 3x faster than medium

print("Starting training...")
results = model.train(
    data="datasets/merged/forensic.yaml",
    epochs=50,
    imgsz=416,
    batch=16,
    name="forensic_v2_fast",
    patience=10,
    workers=2,
    device="cpu",
    fraction=0.3,
    save=True,
    verbose=True,
)

print("Training complete!")
print("Best weights: runs/detect/forensic_v2_fast/weights/best.pt")