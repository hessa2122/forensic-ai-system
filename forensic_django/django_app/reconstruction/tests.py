from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from cases.models import Case
from evidence.models import Evidence
from reconstruction.scene_builder import build_scene


def image_upload():
    buffer = BytesIO()
    Image.new("RGB", (64, 48), (120, 80, 60)).save(buffer, format="JPEG")
    return SimpleUploadedFile("scene.jpg", buffer.getvalue(), content_type="image/jpeg")


class ReconstructionEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="investigator", password="pass12345")
        self.user.profile.is_approved = True
        self.user.profile.save(update_fields=["is_approved"])
        self.case = Case.objects.create(title="Recon case", case_number="CASE-RECON", created_by=self.user)
        self.evidence = Evidence.objects.create(
            case=self.case,
            uploaded_by=self.user,
            file=image_upload(),
            original_filename="scene.jpg",
            status="analyzed",
        )
    @mock.patch("reconstruction.views.build_scene")
    def test_reconstruct_returns_mesh_urls(self, build_scene):
        def fake_build_scene(image_path, glb_out, ply_out, depth_out):
            Path(glb_out).write_bytes(b"glb")
            Path(ply_out).write_text("ply\n", encoding="utf-8")
            Path(depth_out).write_bytes(b"png")
            return {
                "total_points": 3,
                "num_clusters": 1,
                "clusters": [{"id": 0, "centroid": [0, 0, 0], "colour": [255, 0, 0], "count": 3}],
                "glb_ok": True,
                "ply_ok": True,
            }

        build_scene.side_effect = fake_build_scene
        self.client.login(username="investigator", password="pass12345")
        response = self.client.post(
            "/reconstruction/reconstruct/",
            data='{"evidence_id": %d}' % self.evidence.id,
            content_type="application/json",
            SERVER_NAME="localhost",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["mesh_url"].endswith(".glb"))
        self.assertTrue(payload["ply_url"].endswith(".ply"))
        self.assertTrue(payload["depth_url"].endswith(".png"))


class SceneBuilderFallbackTests(TestCase):
    @mock.patch("reconstruction.scene_builder._import_trimesh", return_value=None)
    def test_build_scene_exports_ply_when_trimesh_is_missing(self, _import_trimesh):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            image_path = tmp_path / "scene.jpg"
            glb_path = tmp_path / "scene.glb"
            ply_path = tmp_path / "scene.ply"
            depth_path = tmp_path / "depth.png"
            Image.new("RGB", (32, 24), (120, 80, 60)).save(image_path)

            meta = build_scene(str(image_path), str(glb_path), str(ply_path), str(depth_path))

            self.assertFalse(meta["glb_ok"])
            self.assertTrue(meta["ply_ok"])
            self.assertTrue(ply_path.exists())
            self.assertTrue(depth_path.exists())
            self.assertEqual(ply_path.read_text(encoding="ascii").splitlines()[0], "ply")
