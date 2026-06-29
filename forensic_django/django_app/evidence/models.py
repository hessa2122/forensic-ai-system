"""
evidence/models.py — FINAL FIXED VERSION
Keeps case and uploaded_by nullable to match your existing database schema.
No field renames. Safe to migrate on a database that already has evidence rows.
"""
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Evidence(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("analyzed", "Analyzed"),
        ("failed", "Failed"),
        ("flagged", "Flagged"),
    ]

    # null=True on ForeignKeys matches your existing DB schema
    case              = models.ForeignKey("cases.Case", on_delete=models.CASCADE,
                                          related_name="evidence_items", null=True, blank=True)
    uploaded_by       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    file              = models.ImageField(upload_to="evidence/%Y/%m/%d/", blank=True, default="")
    analysis_image    = models.ImageField(upload_to="evidence/analysis/%Y/%m/%d/", blank=True, default="")
    evidence_type     = models.CharField(max_length=30, blank=True, default="image")
    original_filename = models.CharField(max_length=255, default="")
    mime_type         = models.CharField(max_length=120, blank=True, default="")
    file_size         = models.BigIntegerField(default=0)
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    uploaded_at       = models.DateTimeField(auto_now_add=True, null=True)
    analyzed_at       = models.DateTimeField(null=True, blank=True)   # keep original field name
    notes             = models.TextField(blank=True, default="")
    analysis_error    = models.TextField(blank=True, default="")
    analysis_started_at = models.DateTimeField(null=True, blank=True)
    analysis_completed_at = models.DateTimeField(null=True, blank=True)
    original_sha256   = models.CharField(max_length=64, blank=True, default="")
    analysis_image_sha256 = models.CharField(max_length=64, blank=True, default="")
    model_versions    = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return f"{self.original_filename}"

    # Alias so templates/views using .created_at still work
    @property
    def created_at(self):
        return self.uploaded_at


class DetectionResult(models.Model):
    evidence        = models.OneToOneField(Evidence, on_delete=models.CASCADE)
    analysis_request = models.OneToOneField(
        "AnalysisRequest", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="detection_result",
    )
    detections_json = models.TextField(default="[]")
    detections      = models.JSONField(blank=True, default=list)
    scene_summary   = models.TextField(blank=True, default="")
    evidence_count  = models.IntegerField(default=0)
    confirmed_count = models.IntegerField(default=0)
    candidate_count = models.IntegerField(default=0)
    weapon_count    = models.IntegerField(default=0)
    blood_count     = models.IntegerField(default=0)
    fingerprint_count = models.IntegerField(default=0)
    scene_type      = models.CharField(max_length=50, default="unknown")
    sources_used    = models.CharField(max_length=100, blank=True, default="")
    source_models   = models.JSONField(blank=True, default=list)
    analysis_duration_ms = models.PositiveIntegerField(default=0)
    annotated_image = models.CharField(max_length=500, blank=True, default="")
    error_state     = models.TextField(blank=True, default="")
    analyzed_at     = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Detections for {self.evidence.original_filename}"


class AnalysisRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    REQUEST_TYPES = [
        ('detection', 'AI Detection'),
        ('reconstruction', '3D Reconstruction'),
    ]

    evidence = models.ForeignKey(Evidence, on_delete=models.CASCADE, related_name='analysis_requests')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='analysis_requests')
    request_type = models.CharField(max_length=30, choices=REQUEST_TYPES, default='detection')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='reviewed_analysis_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')
    processing_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-requested_at']
        constraints = [
            models.UniqueConstraint(
                fields=['evidence', 'request_type'],
                condition=models.Q(status__in=['pending', 'approved', 'processing']),
                name='unique_active_analysis_request_per_evidence_type',
            ),
        ]

    def __str__(self):
        return f'Analysis request for {self.evidence}'
