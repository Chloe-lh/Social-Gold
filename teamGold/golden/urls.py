from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from . import apiViews

'''
This registers all views
'''
urlpatterns = [
    path("", views.index, name="index"),
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("signup/", views.signup, name="signup"),
    path('profile/', views.profile_view, name='profile'),
    path('search/', views.search_authors, name='search_authors'),
    path('followers/', views.followers, name='followers'),
    path('following/', views.following, name='following'),
    path("home/", views.home, name="home"),
    # API end points
    # API views will be visible in /swagger/
    path("api/Profile/<str:id>/", apiViews.GETProfileAPIView.as_view()),
    path("api/Entry/<str:id>/", apiViews.GETEntryAPIView.as_view()),
    path("api/Node/<str:id>/", apiViews.GETNodeAPIView.as_view()),
]
    

