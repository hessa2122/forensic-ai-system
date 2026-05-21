# ForensicAI — 3D Crime Scene Detection System

AI-powered forensic evidence detection and 3D crime scene reconstruction.

## Tech Stack
- Django 4.2 + PostgreSQL
- YOLOv8 (weapon detection — 6 classes)
- Open3D (3D point cloud reconstruction)
- Depth Anything V2 (2D → 3D depth estimation)
- Three.js (browser 3D viewer)

## Detected Classes
Grenade · Gun · Knife · Pistol · Handgun · Rifle

## Setup Instructions

### 1. Clone the repository
git clone https://github.com/Master-Lee369/Forensic_3D_Detection-
cd Forensic_3D_Detection-

### 2. Create virtual environment
python -m venv venv_forensic
venv_forensic\Scripts\activate        # Windows
source venv_forensic/bin/activate     # Mac/Linux

### 3. Install dependencies
cd forensic_django/django_app
pip install -r requirements.txt

### 4. Set up PostgreSQL
- Install PostgreSQL from https://postgresql.org
- Create database:
  psql -U postgres -h localhost
  CREATE DATABASE forensic_db;
  CREATE USER forensic_user WITH PASSWORD 'forensic123';
  GRANT ALL PRIVILEGES ON DATABASE forensic_db TO forensic_user;
  ALTER DATABASE forensic_db OWNER TO forensic_user;
  \q

### 5. Create .env file
Create a file called .env inside django_app/ with:
  SECRET_KEY=django-insecure-forensic-change-this-in-production
  DEBUG=True
  DB_NAME=forensic_db
  DB_USER=forensic_user
  DB_PASSWORD=forensic123
  DB_HOST=localhost
  DB_PORT=5432

### 6. Run migrations
python manage.py migrate
python manage.py createsuperuser

### 7. Start server
python manage.py runserver

Open http://127.0.0.1:8000/

## Project Structure
forensic_django/django_app/
├── cases/              Case management
├── evidence/           YOLO weapon detection
│   └── weights/        forensic_best.pt model
├── reconstruction/     Open3D 3D scene builder
├── accounts/           User authentication
├── templates/          Frontend UI
└── media/              Uploaded evidence files