from django.urls import path
from . import views

urlpatterns = [
    path("", views.base, name="base"),
    path('profile/', views.profile_view, name='profile'),
]