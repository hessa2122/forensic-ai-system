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
        ("pending",  "Pending"),
        ("analyzed", "Analyzed"),
        ("flagged",  "Flagged"),
    ]

    # null=True on ForeignKeys matches your existing DB schema
    case              = models.ForeignKey("cases.Case", on_delete=models.CASCADE,
                                          related_name="evidence_items", null=True, blank=True)
    uploaded_by       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    file              = models.ImageField(upload_to="evidence/%Y/%m/%d/", blank=True, default="")
    original_filename = models.CharField(max_length=255, default="")
    file_size         = models.BigIntegerField(default=0)
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    analyzed_at       = models.DateTimeField(default=timezone.now)   # keep original field name
    notes             = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-analyzed_at"]

    def __str__(self):
        return f"{self.original_filename}"

    # Alias so templates/views using .created_at still work
    @property
    def created_at(self):
        return self.analyzed_at


class DetectionResult(models.Model):
    evidence        = models.OneToOneField(Evidence, on_delete=models.CASCADE)
    detections_json = models.TextField(default="[]")
    scene_summary   = models.TextField(blank=True, default="")
    evidence_count  = models.IntegerField(default=0)
    scene_type      = models.CharField(max_length=50, default="unknown")
    sources_used    = models.CharField(max_length=100, blank=True, default="")
    analyzed_at     = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Detections for {self.evidence.original_filename}"


class AnalysisRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]

    evidence = models.ForeignKey(Evidence, on_delete=models.CASCADE, related_name='analysis_requests')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='analysis_requests')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='reviewed_analysis_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f'Analysis request for {self.evidence}'
