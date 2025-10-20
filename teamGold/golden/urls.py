from django.urls import path
from . import views
from . import apiViews

'''
These URL Patterns registers all views 
'''
urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.CustomLoginView.as_view(template_name = "login.html"), name="login"),
    path("signup/", views.signup, name="signup"),
    path('profile/', views.profile_view, name='profile'),
    path('search/', views.search_authors, name='search_authors'),
    path('followers/', views.followers, name='followers'),
    path('following/', views.following, name='following'),
    path("home/", views.home, name="home"),
    # API end points
    # API views will be visible in /swagger/
    # Switched from <str:id> to <path:id> for file and URL flexibility
    path("api/Profile/<path:id>/", apiViews.GETProfileAPIView.as_view(), name="get-profile"),
    path("api/Entry/<path:id>/", apiViews.GETEntryAPIView.as_view(), name="get-entry"),
    path("api/Node/<path:id>/", apiViews.GETNodeAPIView.as_view(), name="get-node"),
    path("api/Follow/<path:id>/", apiViews.GETFollowAPIView.as_view(), name="get-follow"),
    path("api/Like/<path:id>/", apiViews.GETLikeAPIView.as_view(), name="get-like"),
    path("api/Comment/<path:id>/", apiViews.GETCommentAPIView.as_view(), name="get-comment"),
    path("api/EntryImage/<int:id>/", apiViews.GETEntryImageAPIView.as_view(), name="get-entry-image")

]
    

