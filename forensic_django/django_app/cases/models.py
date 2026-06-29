"""
cases/models.py
Stores forensic cases and links to evidence + reconstructions.
"""
from django.db import models
from django.contrib.auth.models import User


class Case(models.Model):

    STATUS_CHOICES = [
        ('open',       'Open'),
        ('active',     'Active Investigation'),
        ('closed',     'Closed'),
        ('archived',   'Archived'),
    ]

    PRIORITY_CHOICES = [
        ('low',      'Low'),
        ('medium',   'Medium'),
        ('high',     'High'),
        ('critical', 'Critical'),
    ]

    # ── Core fields ──────────────────────────────────────────────
    title          = models.CharField(max_length=255)
    case_number    = models.CharField(max_length=50, unique=True)
    description    = models.TextField(blank=True)
    location       = models.CharField(max_length=255, blank=True)
    incident_date  = models.DateField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority       = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')

    # ── Ownership ─────────────────────────────────────────────────
    created_by     = models.ForeignKey(User, on_delete=models.SET_NULL,
                                       null=True, related_name='cases_created')
    assigned_to    = models.ForeignKey(User, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='cases_assigned')

    # ── Timestamps ────────────────────────────────────────────────
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Case #{self.case_number} — {self.title}"

    def evidence_count(self):
        return self.evidence_items.count()

    def get_priority_color(self):
        return {
            'low':      '#22c55e',
            'medium':   '#3b82f6',
            'high':     '#f59e0b',
            'critical': '#ef4444',
        }.get(self.priority, '#6b7280')


class SystemService(models.Model):
    SERVICE_TYPE_CHOICES = [
        ('ai_analysis', 'AI Analysis'),
        ('visualization', 'Visualization'),
    ]

    name = models.CharField(max_length=100, unique=True)
    service_type = models.CharField(max_length=30, choices=SERVICE_TYPE_CHOICES)
    is_enabled = models.BooleanField(default=True)
    config = models.JSONField(blank=True, default=dict)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Report(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='reports')
    evidence = models.ForeignKey('evidence.Evidence', on_delete=models.SET_NULL, null=True, blank=True, related_name='reports')
    detection_result = models.ForeignKey('evidence.DetectionResult', on_delete=models.SET_NULL, null=True, blank=True, related_name='reports')
    reconstruction = models.ForeignKey('reconstruction.SceneReconstruction', on_delete=models.SET_NULL, null=True, blank=True, related_name='reports')
    report_title = models.CharField(max_length=255)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='generated_reports')
    file = models.FileField(upload_to='reports/%Y/%m/', blank=True, default='')
    checksum_sha256 = models.CharField(max_length=64, blank=True, default='')
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return self.report_title
