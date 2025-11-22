from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

# API view imports (use the modules under golden.api)
from .api.profileAPIView import ProfileAPIView
from .api.nodeAPIView import NodeAPIView
from .api.friendsAPIView import AuthorFriendsView, FollowAPIView
from .api.entryAPIView import EntryAPIView, EntryImageAPIView
from .api.commentAPIView import EntryCommentAPIView, SingleCommentAPIView
from .api.likeAPIView import LikeAPIView
from .api.inbox import InboxView

'''
These URL Patterns registers all views 
'''
urlpatterns = [
    path("", views.stream_view, name="stream"),
    path("new_edit_entry/", views.new_edit_entry_view, name="new_edit_entry_view"),
    path("login/", views.CustomLoginView.as_view(template_name="login.html"), name="login"),
    path("signup/", views.signup, name="signup"),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path("authors/<path:author_id>/", views.public_profile_view, name="public-profile"),
    path('profile/followers/', views.followers, name='followers'),
    path('profile/following/', views.following, name='following'),
    path("profile/follow_requests/", views.follow_requests, name="follow_requests"),
    path('entry/<str:entry_uuid>/', views.entry_detail_view, name='entry_detail'),
    path('stream/', views.stream_view, name="stream-link"),

    # Follow-related actions for views
    path('profile/follow/', views.follow_action, name="follow-action"),  # Handle follow
    path('profile/accept_follow/', views.accept_follow_action, name="accept-follow-action"),  # Accept follow
    path('profile/reject_follow/', views.reject_follow_action, name="reject-follow-action"),  # Reject follow
    path('profile/unfollow/', views.unfollow_action, name="unfollow-action"),  # Unfollow action

    # API Endpoints
    path("api/Profile/<path:id>/", ProfileAPIView.as_view(), name="get-profile"),
    path("api/Node/<path:id>/", NodeAPIView.as_view(), name="get-node"),
    path("api/Follow/<path:id>/", FollowAPIView.as_view(), name="get-follow"),
    path("api/Author/<path:author_id>/friends/", AuthorFriendsView.as_view()),
    path("api/Like/<path:id>/", LikeAPIView.as_view(), name="get-like"),

    # Entry-related API
    path("api/Entry/<path:entry_id>/comments/", EntryCommentAPIView.as_view(), name="entry-comments-alias"),
    path("api/Entry/<path:id>/", EntryAPIView.as_view(), name="get-entry"),

    # Follow-related API Endpoints
    path("api/Follow/<path:author_id>/request/", views.api_follow_request, name="api-follow-request"),
    path("api/Follow/<path:author_id>/accept/", views.api_accept_follow, name="api-accept-follow"),
    path("api/Follow/<path:author_id>/reject/", views.api_reject_follow, name="api-reject-follow"),
    path("api/Follow/<path:author_id>/unfollow/", views.api_unfollow, name="api-unfollow"),

    # Comments
    path("api/authors/<path:author_serial>/entries/<path:entry_serial>/comments/", EntryCommentAPIView.as_view(), name="author-entry-comments"),
    path("api/authors/<path:author_serial>/entries/<path:entry_serial>/likes/", LikeAPIView.as_view(), name="author-entry-likes"),

    # Miscellaneous API Endpoints
    path("api/authors/", views.remote_authors_list, name='remote-authors-list'),
    path("api/authors/<uuid:author_id>/inbox/", views.inbox_view, name="author-inbox"),

    path("friends/", views.friends, name="friends"),
    path('add_comment/', views.add_comment, name = "add_comment"),
    path('add_like/', views.toggle_like, name='add_like'),
    path("node_admin/", views.profile_view, name="node_admin"), 
]
    
