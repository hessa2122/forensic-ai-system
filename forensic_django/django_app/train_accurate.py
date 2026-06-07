from ultralytics import YOLO

# Start from existing trained weights (transfer learning)
model = YOLO("runs/detect/forensic_v2_fast-2/weights/best.pt")

results = model.train(
    data="datasets/merged/forensic.yaml",
    epochs=100,          # more epochs
    imgsz=640,           # full resolution
    batch=4,             # small batch for CPU
    name="forensic_v3_accurate",
    patience=15,
    workers=2,
    device="cpu",
    fraction=1.0,        # use ALL data this time
    
    # Better augmentation for forensic images
    augment=True,
    hsv_h=0.02,
    hsv_s=0.8,
    hsv_v=0.5,
    fliplr=0.5,
    flipud=0.1,
    mosaic=0.8,
    
    save=True,
    save_period=5,
    verbose=True,
)

print("Training complete!")
print("Best model: runs/detect/forensic_v3_accurate/weights/best.pt")