from django.urls import path
from . import views, apiViews
from django.contrib.auth import views as auth_views

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
    path("follow_requests/", views.follow_requests, name="follow_requests"),
    path("friends/", views.friends, name="friends"),
    path("home/", views.home, name="home"),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('stream/', views.stream_view, name = 'stream'),
    path('add_comment/', views.add_comment, name = "add_comment"),
    # API end points
    # API views will be visible in /swagger/
    # Switched from <str:id> to <path:id> for file and URL flexibility
    path("api/Profile/<path:id>/", apiViews.ProfileAPIView.as_view(), name="get-profile"),
    path("api/Entry/<path:id>/", apiViews.EntryAPIView.as_view(), name="get-entry"),
    path("api/Node/<path:id>/", apiViews.NodeAPIView.as_view(), name="get-node"),
    path("api/Follow/<path:id>/", apiViews.FollowAPIView.as_view(), name="get-follow"),
    path("api/Like/<path:id>/", apiViews.LikeAPIView.as_view(), name="get-like"),
    path("api/Comment/<path:id>/", apiViews.CommentAPIView.as_view(), name="get-comment"),
    path("api/EntryImage/<int:id>/", apiViews.EntryImageAPIView.as_view(), name="get-entry-image")
]
    

