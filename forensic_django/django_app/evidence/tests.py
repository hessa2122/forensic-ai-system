from io import BytesIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from cases.models import Case
from evidence.model_registry import (
    CONFIRMED_FORENSIC_CLASSES,
    MODEL_REGISTRY,
    candidate_count,
    clamp_bbox,
    confirmed_count,
    dedupe_detections,
    normalize_label,
    weapons_found,
)
from evidence.services.detection_pipeline import MODEL_SPECS, count_label, display_label, get_model_health
from evidence.models import DetectionResult, Evidence
from evidence.views import _validate_uploaded_image


def image_upload(name="evidence.jpg", fmt="JPEG", size=(80, 60), color=(120, 20, 20)):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


class EvidenceUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="investigator", password="pass12345")
        self.user.profile.is_approved = True
        self.user.profile.save(update_fields=["is_approved"])
        self.case = Case.objects.create(
            title="Upload case",
            case_number="CASE-UPLOAD-1",
            created_by=self.user,
        )

    def test_unauthenticated_upload_rejected(self):
        response = self.client.post(reverse("upload_evidence", args=[self.case.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    @mock.patch("evidence.views.analyze_image")
    def test_authorized_valid_jpeg_upload_preserves_original_and_saves_result(self, analyze_image):
        analyze_image.return_value = {
            "detections": [],
            "scene_summary": "No confirmed detections.",
            "confirmed_count": 0,
            "candidate_count": 0,
            "sources_used": [],
            "source_models": [],
        }
        self.client.login(username="investigator", password="pass12345")
        uploaded = image_upload()
        original_bytes = uploaded.read()
        uploaded.seek(0)
        response = self.client.post(
            reverse("upload_evidence", args=[self.case.id]),
            {"evidence_files": [uploaded]},
        )
        self.assertEqual(response.status_code, 302)
        evidence = Evidence.objects.get()
        self.assertEqual(evidence.status, "analyzed")
        self.assertEqual(evidence.original_sha256, __import__("hashlib").sha256(original_bytes).hexdigest())
        self.assertTrue(DetectionResult.objects.filter(evidence=evidence).exists())

    def test_text_file_renamed_as_jpg_rejected_by_content(self):
        fake = SimpleUploadedFile("fake.jpg", b"not really an image", content_type="image/jpeg")
        with self.assertRaisesMessage(Exception, "File content is not a supported image."):
            _validate_uploaded_image(fake)

    @override_settings(EVIDENCE_MAX_UPLOAD_SIZE=10)
    def test_oversized_file_rejected(self):
        with self.assertRaisesMessage(Exception, "File is too large"):
            _validate_uploaded_image(image_upload())

    @mock.patch("evidence.views.analyze_image")
    def test_detection_failure_sets_failed_status(self, analyze_image):
        analyze_image.side_effect = RuntimeError("detector unavailable")
        self.client.login(username="investigator", password="pass12345")
        response = self.client.post(
            reverse("upload_evidence", args=[self.case.id]),
            {"evidence_files": [image_upload()]},
        )
        self.assertEqual(response.status_code, 302)
        evidence = Evidence.objects.get()
        self.assertEqual(evidence.status, "failed")
        self.assertIn("Analysis failed", evidence.analysis_error)


class DetectionRegistryTests(TestCase):
    def test_fingerprint_support_requires_matching_configured_weights(self):
        self.assertIn("fingerprint", MODEL_SPECS["forensic_fingerprint_v1"]["intended_classes"])
        health = get_model_health(load_classes=False)
        fingerprint = next(item for item in health if item["model_name"] == "forensic_fingerprint_v1")
        self.assertFalse(fingerprint["ready"])

    def test_blood_and_shell_casing_normalization(self):
        self.assertEqual(normalize_label("blood stain"), "blood_stain")
        self.assertEqual(normalize_label("bloodstain"), "blood_stain")
        self.assertEqual(normalize_label("shell casing"), "shell_casing")
        self.assertEqual(display_label("blood_stain"), "Blood Stain")
        self.assertEqual(display_label("fingerprint"), "Fingerprint")

    def test_bbox_clamping_and_invalid_rejection(self):
        self.assertEqual(clamp_bbox([-10, 5, 120, 70], 100, 50), [0, 5, 99, 49])
        self.assertIsNone(clamp_bbox([10, 10, 5, 20], 100, 50))
        self.assertIsNone(clamp_bbox(None, 100, 50))

    def test_class_aware_duplicate_removal(self):
        detections = [
            {"label": "blood_stain", "confidence": 0.7, "bbox": [0, 0, 20, 20]},
            {"label": "blood_stain", "confidence": 0.9, "bbox": [1, 1, 21, 21]},
            {"label": "knife", "confidence": 0.8, "bbox": [1, 1, 21, 21]},
        ]
        kept = dedupe_detections(detections)
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[0]["confidence"], 0.9)

    def test_weapon_calculation_excludes_blood_and_candidates(self):
        detections = [
            {"label": "blood_stain", "verification_status": "model_detected"},
            {"label": "possible_fingerprint_like_ridge_region", "verification_status": "candidate_unverified"},
        ]
        self.assertFalse(weapons_found(detections))
        self.assertEqual(confirmed_count(detections), 1)
        self.assertEqual(candidate_count(detections), 1)
        self.assertEqual(count_label(detections, {"blood_stain"}), 1)
        self.assertEqual(count_label(detections, {"fingerprint"}), 0)
