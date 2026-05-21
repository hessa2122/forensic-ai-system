# evidence/models.py

from django.db import models
from cases.models import Case


class Evidence(models.Model):
    THREAT_CHOICES = [
        ('LOW',    'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH',   'High'),
    ]

    case         = models.ForeignKey(Case, on_delete=models.CASCADE,
                                     null=True, blank=True,
                                     related_name='evidence_items')
    image        = models.ImageField(upload_to='evidence_uploads/')
    detections   = models.TextField(default='[]')   # JSON list
    summary      = models.TextField(default='{}')   # JSON dict
    threat_level = models.CharField(max_length=10,
                                    choices=THREAT_CHOICES,
                                    default='LOW')
    analyzed_at  = models.DateTimeField(auto_now_add=True)
    notes        = models.TextField(blank=True)

    class Meta:
        ordering = ['-analyzed_at']

    def __str__(self):
        return f"Evidence #{self.pk} — {self.threat_level}"

    def get_detections(self):
        import json
        return json.loads(self.detections)

    def get_summary(self):
        import json
        return json.loads(self.summary)