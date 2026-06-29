# Initial Audit

## Baseline

- Branch: `fix/evidence-detection-pipeline`
- Initial `git status --short`: clean
- Initial `python manage.py check`, `showmigrations`, and `test`: blocked because Django was not installed in the active Python environment.

## Working Features Found

- Django built-in `auth.User` is used for authentication.
- `UserProfile` exists with approval, role, badge, department, phone, approval metadata, and timestamps.
- Case CRUD/list APIs already enforce basic created-by/assigned-to filtering.
- Evidence upload validates decoded image content and preserves the uploaded file.
- A canonical detection pipeline exists in `evidence/services/detection_pipeline.py`; legacy detector modules mostly wrap it.
- Basic reconstruction pipeline and Three.js viewer endpoints exist.
- Admin registrations exist for core models.

## Broken or Risky Features Found

- Evidence upload ran AI analysis immediately, bypassing analysis-request approval.
- `Evidence.analyzed_at` was populated at upload time.
- `AnalysisRequest` lacked processing, failed, cancelled, request type, rejection reason, processing timestamps, and error fields.
- Reconstruction `_media_path()` returned `None` before trying `field.path`.
- Reconstruction scene-data endpoint referenced undefined `ply_url`.
- Report download did not enforce case object-level permission.
- Report PDF was not persisted as a `Report` database record.
- Backup command only emitted JSON fixture dumps and did not create checksum-tracked database backups.
- Requirements pinned incompatible packages and listed both `opencv-python` and `opencv-python-headless`.

## Missing Synopsis Features

- Persistent notification records.
- Persistent report records.
- Backup records.
- Approval-first analysis workflow.
- PostgreSQL environment-based settings.
- Corrected system-design documentation.

## Duplicate Implementations

- `ai_detector.py`, `model_registry.py`, and related detector files are compatibility wrappers; active detection logic is concentrated in `evidence/services/detection_pipeline.py`.

## Security Problems

- Report object access could be bypassed by changing a case ID.
- Upload-triggered detection bypassed the required admin approval step.
- Old backup command was not an auditable database backup record.

## Model Files Found

- `evidence/weights/forensic_best.pt`
- `evidence/weights/forensic_best_v2.pt`
- `evidence/weights/yolov8m.pt`

## Actual Classes Inspected with Ultralytics

- `forensic_best.pt`: `grenade`, `gun`, `handgun`, `knife`, `pistol`, `rifle`
- `forensic_best_v2.pt`: `blood_stain`, `grenade`, `gun`, `knife`, `pistol`, `rifle`, `shell_casing`
- Blood-specific weights: not configured.
- Fingerprint-specific weights: not configured.

## Database and Migration Condition

- Existing migrations were applied through `accounts.0002`, `cases.0002`, `evidence.0005`, and `reconstruction.0001`.
- New additive migrations were created for notifications, backups, reports, and request workflow fields.

## Current Test Failures at Audit Time

- Tests initially could not run because Django was missing.
- After dependency installation, old upload tests failed because they expected immediate analysis; tests were updated to assert pending-by-default upload and approved request execution.
