from django.urls import path
from . import views

urlpatterns = [
    path('reconstruct/',                    views.reconstruct_direct,          name='reconstruct'),
    path('reconstruct/<int:evidence_id>/',  views.reconstruct_from_evidence,   name='reconstruct-from-evidence'),
    path('reconstructions/',                views.reconstruction_list,         name='reconstruction-list'),
    path('reconstruction-data/<int:scene_id>/', views.point_cloud_data,         name='reconstruction-data'),
    path('scene/<int:scene_id>/',           views.scene_viewer,                name='scene-viewer'),
    path('scene/',                          views.scene_viewer,                name='scene-viewer-new'),
]
