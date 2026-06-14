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

    # ── Output files ──────────────────────────────────────────────────────────
    ply_file  = models.FileField(
                    upload_to='scenes/pointclouds/%Y/%m/',
                    null=True, blank=True)
    depth_map = models.ImageField(
                    upload_to='scenes/depthmaps/%Y/%m/',
                    null=True, blank=True)

    # ── Scene metadata ────────────────────────────────────────────────────────
    scene_name     = models.CharField(max_length=255, blank=True)
    total_points   = models.IntegerField(default=0)
    num_clusters   = models.IntegerField(default=0)
    clusters_json  = models.JSONField(default=list, blank=True)

    # ── Status ─────────────────────────────────────────────────────────────────
    success       = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Scene #{self.pk} — {self.scene_name}"