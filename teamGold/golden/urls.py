from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("", views.index, name="index"),
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("signup/", views.signup, name="signup"),
    path('profile/', views.profile_view, name='profile'),
    path('search/', views.search_authors, name='search_authors'),
    path('followers/', views.followers, name='followers'),
    path('following/', views.following, name='following'),
    path("follow_requests/", views.follow_requests, name="follow_requests"),
    path("home/", views.home, name="home"),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]
    

