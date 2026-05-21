
from roboflow import Roboflow

rf = Roboflow(api_key="D93tNWgJYVe4S3BLkcV7")

print("Downloading weapon dataset 2...")

project2 = rf.workspace("parthav-joshi").project("weapon_detection-xbxnv")

project2.version(1).download("yolov8", location="datasets/weapons2")

print("Downloading blood dataset 1...")

project3 = rf.workspace("ghalya-hxgho").project("bloodstain-z2fox")

project3.version(1).download("yolov8", location="datasets/blood")

print("Downloading blood dataset 2...")

project4 = rf.workspace("wsaif").project("blood-detection-po83l-qzjgh")

project4.version(1).download("yolov8", location="datasets/blood2")

print("All done!")
