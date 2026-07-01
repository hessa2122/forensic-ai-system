# ForensicAI - 3D Crime Scene Detection System

AI-powered forensic evidence detection and approximate 3D crime scene reconstruction.

## Local Setup (Windows PowerShell)

```powershell
cd forensic_django\django_app

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-ml.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py check
python manage.py check_forensic_models
python manage.py check_reconstruction_stack
python manage.py test
python manage.py runserver
```

SQLite works by default. PostgreSQL remains optional through the database
environment variables in `forensic_django\django_app\.env.example`.

## Workflow

```text
registration -> admin approval -> admin case assignment -> evidence upload
-> detection/reconstruction request -> admin approval -> processing -> saved result
-> notification -> result/report review -> audit log
```

Normal users cannot directly run detection or reconstruction. Requests must be
approved by an admin before processing.

## Detection Classes

The canonical local detection classes are:

```text
gun
knife
grenade
blood_stain
fingerprint
footprint
```

Configure trained local YOLO weights with:

```text
FORENSIC_COMBINED_WEIGHTS
FORENSIC_WEAPON_WEIGHTS
FORENSIC_TRACE_WEIGHTS
FORENSIC_BLOOD_WEIGHTS
FORENSIC_FINGERPRINT_WEIGHTS
FORENSIC_FOOTPRINT_WEIGHTS
```

Run `python manage.py check_forensic_models` to inspect the actual classes in
each `.pt` file. A filename is not treated as proof of supported classes.

Accuracy depends on dataset quality, annotation quality, class balance, image
quality, model training, threshold calibration, and independent test-set
evaluation. Do not claim accuracy without a real evaluation report.

OpenCV colour/ridge heuristics may produce only `candidate_unverified` records.
They are not counted as confirmed blood, fingerprint or footprint evidence.

## 3D Reconstruction

Single-image 3D reconstruction is an AI-generated approximate reconstruction
for visual investigation support. It is not a substitute for calibrated forensic
photogrammetry.

Use `python manage.py check_reconstruction_stack` to verify Open3D, trimesh,
torch, transformers, CUDA status, and writable media output directories.
