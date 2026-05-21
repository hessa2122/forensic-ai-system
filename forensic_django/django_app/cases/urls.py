from django.urls import path
from . import views

urlpatterns = [
    path('cases/',          views.CaseListView.as_view(),   name='case-list'),
    path('cases/<int:pk>/', views.CaseDetailView.as_view(), name='case-detail'),
    path('stats/',          views.DashboardStatsView.as_view(), name='stats'),
]

