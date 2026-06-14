from roboflow import Roboflow

rf = Roboflow(api_key="D93tNWgJYVe4S3BLkcV7")

# Dataset 1: Weapons (9.6k images - Pistol, Knife, Rifle, Grenade, Missile)
print("Downloading weapon dataset...")
project = rf.workspace("test-7awfy").project("weapon-detection-f1lih")
project.version(1).download("yolov8", location="datasets/weapons")

# Dataset 2: Weapons with more classes (2.8k images - knife, rifle, ak, cleaver etc)
print("Downloading weapon dataset 2...")
project2 = rf.workspace("rhackathon").project("weapon-detection-aoxpz")
project2.version(1).download("yolov8", location="datasets/weapons2")

# Dataset 3: Blood detection (326 images)
print("Downloading blood dataset...")
project3 = rf.workspace("ghalya-hxgho").project("bloodstain-z2fox")

project3.version(1).download("yolov8", location="datasets/blood")

# Dataset 4: Blood detection larger (3.2k images)
print("Downloading blood dataset 2...")
project4 = rf.workspace("wsaif").project("blood-detection-po83l-qzjgh")
project4.version(1).download("yolov8", location="datasets/blood2")

print("\nAll datasets downloaded! Check the datasets/ folder.")