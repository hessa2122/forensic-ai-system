from django.urls import path
from . import views

urlpatterns = [
    path('upload/',                         views.api_upload_evidence, name='api_upload_evidence'),
    path('case/<int:case_id>/upload/',         views.upload_evidence,   name='upload_evidence'),
    path('case/<int:case_id>/',                views.evidence_list,     name='evidence_list'),
    path('<int:evidence_id>/',                 views.evidence_detail,   name='evidence_detail'),
    path('<int:evidence_id>/request-analysis/', views.submit_analysis_request, name='submit_analysis_request'),
    path('<int:evidence_id>/reanalyze/',       views.reanalyze_evidence, name='reanalyze_evidence'),
    path('<int:evidence_id>/delete/',          views.delete_evidence,   name='delete_evidence'),
    path('requests/<int:request_id>/approve/', views.approve_analysis_request, name='approve_analysis_request'),
    path('requests/<int:request_id>/reject/',  views.reject_analysis_request, name='reject_analysis_request'),
]
