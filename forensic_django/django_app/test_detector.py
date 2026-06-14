import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'forensic_project.settings')
django.setup()

from evidence.ai_detector import analyze_image

# Use any real image file on your PC - change this path
result = analyze_image(r"C:\Users\Dell\Pictures\free-photo-of-photo-of-a-hand-holding-a-gun.jpeg")

print('Detections:', len(result['detections']))
for d in result['detections']:
    print(f"  [{d['source']}] {d['label']} - {d['confidence']*100:.0f}%")
print('Summary:', result['scene_summary'])