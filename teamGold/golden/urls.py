from django.urls import path
from . import views
from .views import base, NodeDetailAPIView

urlpatterns = [
    path("", views.base, name="base"),
     path('api/node/<path:id>/', NodeDetailAPIView.as_view, name="node-details"),
]