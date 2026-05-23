from django.urls import path
from .views import CaseListView, CaseDetailView, StatsView

urlpatterns = [
    path("cases/",          CaseListView.as_view(),   name="case-list"),
    path("cases/<int:pk>/", CaseDetailView.as_view(), name="case-detail"),
    path("stats/",          StatsView.as_view(),      name="stats"),
]