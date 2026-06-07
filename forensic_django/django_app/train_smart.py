from ultralytics import YOLO

# Start from existing weights (faster convergence)
model = YOLO("runs/detect/forensic_v2_fast-2/weights/best.pt")

results = model.train(
    data="datasets/merged/forensic.yaml",
    epochs=50,
    imgsz=512,       # compromise between 416 and 640
    batch=8,
    name="forensic_v3_smart",
    patience=10,
    workers=2,
    device="cpu",
    fraction=0.5,    # 50% of data — much faster, still good accuracy
    augment=True,
    save=True,
    save_period=5,
    verbose=True,
)

print("Done! Best weights: runs/detect/forensic_v3_smart/weights/best.pt")