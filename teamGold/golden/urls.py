from django.urls import path
from . import views
from .views import base, NodeDetailAPIView

urlpatterns = [
    path("", views.base, name="base"),
    path('profile/', views.profile_view, name='profile'),
    path('api/node/<path:id>/', NodeDetailAPIView.as_view, name="node-details"),
]