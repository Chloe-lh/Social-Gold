from django.urls import path
from . import views, apiViews
from django.contrib.auth import views as auth_views

'''
These URL Patterns registers all views 
'''
urlpatterns = [
    path("", views.home, name="home"),
    path("new_post/", views.new_post, name="new_post"),
    path("login/", views.CustomLoginView.as_view(template_name = "login.html"), name="login"),
    path("signup/", views.signup, name="signup"),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    path('profile/', views.profile_view, name='profile'),
    # profile should contain: main profile that contains a list of the author's entries
    # profile also contains the following: followers, following, and requests
    path('profile/followers/', views.followers, name='followers'),
    path('profile/following/', views.following, name='following'),
    path("profile/follow_requests/", views.follow_requests, name="follow_requests"),

    path('entry/<uuid:entry_uuid>/', views.entry_detail, name='entry_detail'),
    # TODO: change the id to be the entry id, whatever we decide to use later
    # TODO: entries can have comment page number queries (Or we just allow infinite scroll for comments..?)
    # TODO: entries should have comments feature if there is a logged in user

    # TODO: the following may be deleted/incorporated into another view
    path('search/', views.search_authors, name='search_authors'),
    path("friends/", views.friends, name="friends"),
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
    path("api/EntryImage/<int:id>/", apiViews.EntryImageAPIView.as_view(), name="get-entry-image"),
    
    path("api/author/<uuid:author_id>/inbox/", views.inbox, name="inbox")
]
    

