"""
reconstruction/models.py
Stores 3D scene reconstruction results.
"""
from django.db import models
from cases.models    import Case
from evidence.models import Evidence


class SceneReconstruction(models.Model):

    # ── Links ─────────────────────────────────────────────────────────────────
    case      = models.ForeignKey(Case, on_delete=models.CASCADE,
                                  related_name='reconstructions')
    evidence  = models.ForeignKey(Evidence, on_delete=models.CASCADE,
                                  null=True, blank=True,
                                  related_name='reconstructions')
    analysis_request = models.OneToOneField(
        'evidence.AnalysisRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scene_reconstruction',
    )

    # ── Output files ──────────────────────────────────────────────────────────
    ply_file  = models.FileField(
                    upload_to='scenes/pointclouds/%Y/%m/',
                    null=True, blank=True)
    glb_file  = models.FileField(
                    upload_to='scenes/pointclouds/%Y/%m/',
                    null=True, blank=True)
    depth_map = models.ImageField(
                    upload_to='scenes/depthmaps/%Y/%m/',
                    null=True, blank=True)

    # ── Scene metadata ────────────────────────────────────────────────────────
    scene_name     = models.CharField(max_length=255, blank=True)
    total_points   = models.IntegerField(default=0)
    vertex_count   = models.IntegerField(default=0)
    triangle_count = models.IntegerField(default=0)
    num_clusters   = models.IntegerField(default=0)
    clusters_json  = models.JSONField(default=list, blank=True)
    mesh_type      = models.CharField(max_length=20, blank=True, default='')
    model_name     = models.CharField(max_length=120, blank=True, default='')
    model_version  = models.CharField(max_length=120, blank=True, default='')
    parameters_json = models.JSONField(default=dict, blank=True)
    output_sha256  = models.CharField(max_length=64, blank=True, default='')

    # ── Status ─────────────────────────────────────────────────────────────────
    success       = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    started_at    = models.DateTimeField(null=True, blank=True)
    completed_at  = models.DateTimeField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Scene #{self.pk} — {self.scene_name}"
