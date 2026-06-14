from django.urls import path
from . import views

urlpatterns = [
    path('reconstruct/',
         views.reconstruct_api,
         name='reconstruct_api'),

    path('reconstructions/',
         views.reconstructions_api,
         name='reconstructions_api'),

    path('reconstruction-data/<int:scene_id>/',
         views.reconstruction_scene_data_api,
         name='reconstruction_scene_data_api'),

    path('<int:evidence_id>/',
         views.reconstruction_view,
         name='reconstruction_view'),

    path('<int:evidence_id>/data/',
         views.reconstruction_data_api,
         name='reconstruction_data'),
]