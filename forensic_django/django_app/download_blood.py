from roboflow import Roboflow
rf = Roboflow(api_key='D93tNWgJYVe4S3BLkcV7')
print('Downloading blood dataset...')
project = rf.workspace('ghalya-hxgho').project('bloodstain-z2fox')
project.version(1).download('yolov8', location='datasets/blood')
print('Done!')