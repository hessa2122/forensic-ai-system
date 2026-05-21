import os, shutil, glob

sources = ["datasets/weapons", "datasets/weapons2", "datasets/blood"]

os.makedirs("datasets/merged/images/train", exist_ok=True)
os.makedirs("datasets/merged/images/val", exist_ok=True)
os.makedirs("datasets/merged/labels/train", exist_ok=True)
os.makedirs("datasets/merged/labels/val", exist_ok=True)

counter = 0
labels_copied = 0
labels_missing = 0

for source in sources:
    for split, out_split in [("train", "train"), ("valid", "val"), ("test", "val")]:
        img_dir = f"{source}/{split}/images"
        lbl_dir = f"{source}/{split}/labels"
        if not os.path.exists(img_dir):
            print(f"Skipping missing: {img_dir}")
            continue
        imgs = glob.glob(f"{img_dir}/*")
        print(f"Found {len(imgs)} images in {img_dir}")
        for img in imgs:
            ext = os.path.splitext(img)[1].lower()
            if ext not in [".jpg", ".jpeg", ".png"]:
                continue
            stem = os.path.splitext(os.path.basename(img))[0]
            dst_img = f"datasets/merged/images/{out_split}/img_{counter:06d}{ext}"
            dst_lbl = f"datasets/merged/labels/{out_split}/img_{counter:06d}.txt"
            shutil.copy(img, dst_img)
            lbl = f"{lbl_dir}/{stem}.txt"
            if os.path.exists(lbl):
                shutil.copy(lbl, dst_lbl)
                labels_copied += 1
            else:
                labels_missing += 1
            counter += 1

print(f"\nImages merged  : {counter}")
print(f"Labels copied  : {labels_copied}")
print(f"Labels missing : {labels_missing}")