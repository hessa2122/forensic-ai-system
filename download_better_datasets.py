from roboflow import Roboflow

rf = Roboflow(api_key="YOUR_API_KEY")

# Best weapon dataset - 9.6k images, 5 classes
print("Downloading weapons...")
rf.workspace("test-7awfy").project("weapon-detection-f1lih").version(1).download(
    "yolov8", location="datasets/weapons_hq")

# Crime scene dataset with blood labels
print("Downloading crime scene...")
rf.workspace("forensic-science-project-lmjha").project("crime-scene-xjbfp").version(1).download(
    "yolov8", location="datasets/crime_scene")

# Shell casing detection  
print("Downloading shell casings...")
rf.workspace("new-workspace-bjaa4").project("knifegun").version(1).download(
    "yolov8", location="datasets/knifegun")

print("Done!")