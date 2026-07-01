# Forensic Model Setup

The core workflow is local-first and does not require paid APIs. Confirmed detections are produced only by trained local YOLO models whose loaded classes match the configured forensic classes.

Configure optional weights with:

```text
FORENSIC_WEAPON_WEIGHTS=evidence/weights/forensic_best.pt
FORENSIC_TRACE_WEIGHTS=evidence/weights/trace_detector.pt
FORENSIC_BLOOD_WEIGHTS=evidence/weights/blood_detector.pt
FORENSIC_FINGERPRINT_WEIGHTS=evidence/weights/fingerprint_detector.pt
FORENSIC_FOOTPRINT_WEIGHTS=evidence/weights/footprint_detector.pt
FORENSIC_COMBINED_WEIGHTS=evidence/weights/combined_forensic.pt
```

Canonical classes:

```text
gun
knife
grenade
blood_stain
fingerprint
footprint
```

Aliases:

```text
gun: gun, firearm, pistol, handgun, hand gun, revolver, rifle
knife: knife, blade, dagger
grenade: grenade, hand grenade
blood_stain: blood, bloodstain, blood stain, blood stains
fingerprint: fingerprint, finger print, latent fingerprint, fingerprint mark
footprint: footprint, foot print, shoe print, shoeprint, footwear impression
```

Run the class-health command:

```text
python manage.py check_forensic_models
```

The command loads each configured YOLO file and reads `model.names`. A filename alone is never treated as proof of supported classes. If any class is absent, the app remains usable but the complete six-class forensic pipeline is reported as not ready.

OpenCV colour/ridge heuristics may only produce `candidate_unverified` records. They are not counted as confirmed blood, fingerprint or footprint evidence.

Accuracy must come from an independent validation or test split. Do not display "high accuracy" unless a saved evaluation report supports it.
