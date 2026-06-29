from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
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
from evidence.services.detection_pipeline import (
    MODEL_SPECS,
    count_label,
    display_label,
    get_model_health,
    run_cv_candidates,
)
from evidence.models import AnalysisRequest, DetectionResult, Evidence
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
    def test_authorized_valid_jpeg_upload_preserves_original_and_stays_pending(self, analyze_image):
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
        self.assertEqual(evidence.status, "pending")
        self.assertEqual(evidence.original_sha256, __import__("hashlib").sha256(original_bytes).hexdigest())
        self.assertFalse(DetectionResult.objects.filter(evidence=evidence).exists())
        analyze_image.assert_not_called()

    def test_text_file_renamed_as_jpg_rejected_by_content(self):
        fake = SimpleUploadedFile("fake.jpg", b"not really an image", content_type="image/jpeg")
        with self.assertRaisesMessage(Exception, "File content is not a supported image."):
            _validate_uploaded_image(fake)

    @override_settings(EVIDENCE_MAX_UPLOAD_SIZE=10)
    def test_oversized_file_rejected(self):
        with self.assertRaisesMessage(Exception, "File is too large"):
            _validate_uploaded_image(image_upload())

    @override_settings(AUTO_ANALYZE_ON_UPLOAD=True)
    @mock.patch("evidence.views.analyze_image")
    def test_auto_analysis_failure_sets_failed_status_when_enabled(self, analyze_image):
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

    def test_api_upload_without_auto_analysis_returns_pending(self):
        self.client.login(username="investigator", password="pass12345")
        response = self.client.post(
            reverse("api_upload_evidence"),
            {"case_id": self.case.id, "image": image_upload()},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["detections"], [])
        self.assertFalse(payload["weapons_found"])

    @mock.patch("evidence.views.analyze_image")
    def test_api_upload_with_run_analysis_returns_detections(self, analyze_image):
        analyze_image.return_value = {
            "detections": [
                {
                    "label": "knife",
                    "display_label": "Knife",
                    "confidence": 0.9,
                    "bbox": [1, 1, 40, 40],
                    "source": "local_yolo",
                    "model_name": "forensic_weapons_v1",
                    "model_version": "forensic_best.pt",
                    "verification_status": "model_detected",
                    "forensic_significance": "high",
                    "description": "Knife detected by trained local model.",
                    "location": "center",
                    "color": "#ef4444",
                    "notes": "",
                }
            ],
            "scene_summary": "1 confirmed detection.",
            "confirmed_count": 1,
            "candidate_count": 0,
            "sources_used": ["local_yolo"],
            "source_models": [{"model_name": "forensic_weapons_v1", "model_version": "forensic_best.pt"}],
        }
        self.client.login(username="investigator", password="pass12345")
        response = self.client.post(
            reverse("api_upload_evidence"),
            {"case_id": self.case.id, "image": image_upload(), "run_analysis": "1"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "analyzed")
        self.assertEqual(payload["total_objects"], 1)
        self.assertTrue(DetectionResult.objects.filter(evidence__status="analyzed").exists())

    @mock.patch("evidence.views.analyze_image")
    def test_uploader_can_run_detection_on_pending_evidence(self, analyze_image):
        analyze_image.return_value = {
            "detections": [
                {
                    "label": "gun",
                    "display_label": "Gun",
                    "confidence": 0.8,
                    "bbox": [5, 5, 55, 45],
                    "source": "local_yolo",
                    "model_name": "forensic_weapons_v1",
                    "model_version": "forensic_best.pt",
                    "verification_status": "model_detected",
                    "forensic_significance": "high",
                    "description": "Gun detected by trained local model.",
                    "location": "center",
                    "color": "#ef4444",
                    "notes": "",
                }
            ],
            "scene_summary": "1 confirmed detection.",
            "confirmed_count": 1,
            "candidate_count": 0,
            "sources_used": ["local_yolo"],
            "source_models": [{"model_name": "forensic_weapons_v1", "model_version": "forensic_best.pt"}],
        }
        self.client.login(username="investigator", password="pass12345")
        evidence = Evidence.objects.create(
            case=self.case,
            uploaded_by=self.user,
            file=image_upload(),
            original_filename="pending.jpg",
            status="pending",
        )

        response = self.client.post(reverse("reanalyze_evidence", args=[evidence.id]))

        self.assertEqual(response.status_code, 200)
        evidence.refresh_from_db()
        self.assertEqual(evidence.status, "analyzed")
        self.assertEqual(DetectionResult.objects.get(evidence=evidence).weapon_count, 1)

    def test_duplicate_active_analysis_request_rejected(self):
        self.client.login(username="investigator", password="pass12345")
        self.client.post(reverse("upload_evidence", args=[self.case.id]), {"evidence_files": [image_upload()]})
        evidence = Evidence.objects.get()
        first = self.client.post(reverse("submit_analysis_request", args=[evidence.id]))
        second = self.client.post(reverse("submit_analysis_request", args=[evidence.id]))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)

    @mock.patch("evidence.views.analyze_image")
    def test_approved_request_runs_analysis_and_stores_result(self, analyze_image):
        analyze_image.return_value = {
            "detections": [],
            "scene_summary": "No confirmed detections.",
            "confirmed_count": 0,
            "candidate_count": 0,
            "sources_used": [],
            "source_models": [],
        }
        admin = User.objects.create_superuser(username="admin", password="pass12345")
        self.client.login(username="investigator", password="pass12345")
        self.client.post(reverse("upload_evidence", args=[self.case.id]), {"evidence_files": [image_upload()]})
        evidence = Evidence.objects.get()
        response = self.client.post(reverse("submit_analysis_request", args=[evidence.id]))
        self.assertEqual(response.status_code, 200)
        analysis_request = AnalysisRequest.objects.get(evidence=evidence)
        self.client.logout()
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(reverse("approve_analysis_request", args=[analysis_request.id]), {"run": "1"})
        self.assertEqual(response.status_code, 200)
        evidence.refresh_from_db()
        analysis_request.refresh_from_db()
        self.assertEqual(evidence.status, "analyzed")
        self.assertEqual(analysis_request.status, "completed")
        self.assertTrue(DetectionResult.objects.filter(evidence=evidence, analysis_request=analysis_request).exists())


class DetectionRegistryTests(TestCase):
    def test_fingerprint_support_requires_matching_configured_weights(self):
        self.assertIn("fingerprint", MODEL_SPECS["forensic_fingerprint_v1"]["intended_classes"])
        health = get_model_health(load_classes=False)
        fingerprint = next(item for item in health if item["model_name"] == "forensic_fingerprint_v1")
        self.assertFalse(fingerprint["ready"])

    def test_only_requested_detection_categories_are_normalized(self):
        self.assertEqual(normalize_label("blood stain"), "blood_stain")
        self.assertEqual(normalize_label("bloodstain"), "blood_stain")
        self.assertEqual(normalize_label("pistol"), "gun")
        self.assertEqual(normalize_label("handgun"), "gun")
        self.assertEqual(normalize_label("rifle"), "gun")
        self.assertIsNone(normalize_label("shell casing"))
        self.assertIsNone(normalize_label("grenade"))
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
            {"label": "fingerprint", "verification_status": "candidate_unverified"},
        ]
        self.assertFalse(weapons_found(detections))
        self.assertEqual(confirmed_count(detections), 1)
        self.assertEqual(candidate_count(detections), 1)
        self.assertEqual(count_label(detections, {"blood_stain"}), 1)
        self.assertEqual(count_label(detections, {"fingerprint"}), 0)

    @override_settings(ENABLE_CV_CANDIDATES=True)
    def test_cv_blood_candidate_detects_dark_red_stain(self):
        with TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "blood.jpg"
            img = Image.new("RGB", (240, 160), (110, 95, 75))
            pixels = img.load()
            for x in range(92, 150):
                for y in range(42, 92):
                    if ((x - 121) ** 2) / 1500 + ((y - 67) ** 2) / 700 <= 1:
                        pixels[x, y] = (92, 8, 6)
            img.save(image_path)

            detections = run_cv_candidates(str(image_path))

            self.assertTrue(any(det["label"] == "blood_stain" for det in detections))
