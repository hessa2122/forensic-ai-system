# Forensic Model Setup

The core workflow is local-first and does not require paid APIs. Confirmed detections are produced only by trained local YOLO models whose loaded classes match the configured forensic classes.

Configure optional weights with:

```text
FORENSIC_WEAPON_WEIGHTS=evidence/weights/forensic_best.pt
FORENSIC_BLOOD_WEIGHTS=evidence/weights/blood_detector.pt
FORENSIC_FINGERPRINT_WEIGHTS=evidence/weights/fingerprint_detector.pt
FORENSIC_COMBINED_WEIGHTS=evidence/weights/combined_forensic.pt
```

Expected class names, including aliases:

```text
blood_stain: blood, bloodstain, blood stain, blood stains
fingerprint: fingerprint, fingerprint mark, latent fingerprint
weapons: gun, pistol, handgun, rifle, knife, grenade
shell_casing: shell casing, bullet casing, cartridge casing
```

Run:

```text
python manage.py verify_forensic_models
```

If blood or fingerprint weights are absent or their real `model.names` do not include those classes, the app remains usable but will not report confirmed Blood Stain or Fingerprint detections. OpenCV visual heuristics may only produce unverified candidates.
