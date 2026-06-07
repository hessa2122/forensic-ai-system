from roboflow import Roboflow
rf = Roboflow(api_key='D93tNWgJYVe4S3BLkcV7')

print('Weapons already downloaded, skipping...')

print('Downloading crime scene dataset (knife, glass, hammer)...')
rf.workspace('crimesceneobjectsdetection').project('crime-scene-oma5u').version(7).download('yolov8', location='datasets/crime_scene')

print('Downloading guns and knives (9.8k images)...')
rf.workspace('crime-detection').project('guns_n_knives-h4bky').version(1).download('yolov8', location='datasets/guns_knives')

print('All done!')