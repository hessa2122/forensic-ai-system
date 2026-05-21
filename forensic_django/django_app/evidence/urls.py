from django.urls import path
from . import views

urlpatterns = [
    path('evidence/upload/', views.analyze_evidence, name='evidence-upload'),
    path('evidence/',        views.evidence_list,    name='evidence-list'),
    path('evidence/<int:pk>/', views.evidence_detail, name='evidence-detail'),
]