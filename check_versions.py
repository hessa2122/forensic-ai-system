from roboflow import Roboflow
rf = Roboflow(api_key='D93tNWgJYVe4S3BLkcV7')
project = rf.workspace('wsaif').project('blood-detection-po83l-qzjgh')
print('Versions available:')
print(project.versions())