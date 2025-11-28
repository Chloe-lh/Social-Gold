from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

# API view imports (use the modules under golden.api)
# Note: `profileAPIView` and `nodeAPIView` were removed in this branch; skip importing them
from .api.friendsAPIView import AuthorFriendsView, FollowAPIView
from .api.entryAPIView import EntryAPIView, EntryImageAPIView, ReadingAPIView, AuthorEntriesView, AuthorEntryView
from .api.commentAPIView import EntryCommentAPIView, SingleCommentAPIView, CommentedAPIView
from .api.likeAPIView import LikeAPIView, LikedAPIView
from .api.authorsAPIView import AuthorsListView, SingleAuthorAPIView
from .api.followersAPIView import FollowersView

'''
These URL Patterns registers all views 
'''
urlpatterns =  [

    # Website Views
    path("", views.stream_view, name="stream"),
    path("login/", views.CustomLoginView.as_view(template_name="login.html"), name="login"),
    path("signup/", views.signup, name="signup"),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('stream/', views.stream_view, name="stream-link"),
    path("new_edit_entry/", views.new_edit_entry_view, name="new_edit_entry_view"),
    path('entry/<str:entry_uuid>/', views.entry_detail_view, name='entry_detail'),
    path("authors/<path:author_id>/", views.public_profile_view, name="public-profile"),
    path('profile/', views.profile_view, name='profile'),
    path('profile/followers/', views.followers, name='followers'),
    path('profile/following/', views.following, name='following'),
    path("profile/follow_requests/", views.follow_requests, name="follow_requests"),

    # Follow Feature Actions
    path('profile/follow/', views.api_follow_action, name="follow-action"), 
    path('profile/accept_follow/', views.api_accept_follow_action, name="accept-follow-action"), 
    path('profile/reject_follow/', views.api_reject_follow_action, name="reject-follow-action"), 
    path('profile/unfollow/', views.api_unfollow_action, name="unfollow-action"),     
    path("api/reading/", ReadingAPIView.as_view(), name="api-reading"),

    # profile and node endpoints removed in this branch
    path("api/Follow/<path:id>/", FollowAPIView.as_view(), name="get-follow"),
    path("api/Author/<path:author_id>/friends/", AuthorFriendsView.as_view()),
    path("api/Like/<path:id>/", LikeAPIView.as_view(), name="get-like"),

    # Entry-related API
    path("api/entries/<path:entry_serial>/comments/", EntryCommentAPIView.as_view(), name="entry-comments-alias"),

    # Backwards-compatible capitalized aliases used by tests
    path("api/Entry/<path:entry_serial>/comments/", EntryCommentAPIView.as_view(), name="entry-comments-alias-cap"),
    path("api/entries/<path:id>/", EntryAPIView.as_view(), name="get-entry"),
    path("api/Entry/<path:id>/", EntryAPIView.as_view(), name="get-entry-cap"),
    path("api/authors/<str:author_serial>/entries/", AuthorEntriesView.as_view(), name="get-author-entries"),
    path("api/authors/<str:author_serial>/entries/<str:entry_serial>", AuthorEntryView.as_view(), name="get-author-entry"),

    # Follow-related API Endpoints
    path("api/authors/<str:author_serial>/followers/<str:foreign_author_fqid>", FollowersView.as_view(), name="api-follower"),
    path("api/Follow/<path:author_id>/request/", views.api_follow_requests, name="api-follow-request"),
    path("api/Follow/<path:author_id>/accept/", views.api_accept_follow_action, name="api-accept-follow"),
    path("api/Follow/<path:author_id>/reject/", views.api_reject_follow_action, name="api-reject-follow"),
    path("api/Follow/<path:author_id>/unfollow/", views.api_unfollow_action, name="api-unfollow"),

    # Comments
    path("api/authors/<path:author_serial>/entries/<path:entry_serial>/comments/", EntryCommentAPIView.as_view(), name="author-entry-comments"),
    path("api/authors/<path:author_serial>/commented", CommentedAPIView.as_view(), name="author-commented"),
    path("api/authors/<path:author_fqid>/commented", CommentedAPIView.as_view(), name="author-commented-fqid"),
    path("api/authors/<path:author_serial>/entries/<path:entry_serial>/comment/<path:comment_fqid>", CommentedAPIView.as_view(), name="author-entry-comments2"),
    path("api/authors/<path:author_serial>/commented/<path:comment_fqid>", CommentedAPIView.as_view(), name="author-comment"),

    # Likes
    path("api/authors/<path:author_serial>/entries/<path:entry_serial>/likes/", LikeAPIView.as_view(), name="author-entry-likes"),
    path("api/authors/<path:author_serial>/entries/<path:entry_serial>/comments/<path:comment_fqid>/likes/", LikeAPIView.as_view(), name="author-entry-comment-likes"),
    path("api/entries/<path:entry_fqid>/likes/", LikeAPIView.as_view(), name="entry-likes"),
    path("api/Entry/<path:entry_fqid>/likes/", LikeAPIView.as_view(), name="entry-likes-cap"),

    # Liked by author endpoints
    path("api/authors/<path:author_serial>/liked/", LikedAPIView.as_view(), name="author-liked"),
    path("api/authors/<path:author_serial>/liked/<path:like_serial>/", LikedAPIView.as_view(), name="author-liked-single"),
    path("api/authors/<path:author_fqid>/liked/", LikedAPIView.as_view(), name="author-liked-fqid"),
    path("api/liked/<path:like_fqid>/", LikedAPIView.as_view(), name="liked"),

    # Authors API Endpoints
    #path("api/authors/<path:author_id>/inbox/", inbox_view)
    path("api/authors/<str:author_id>/inbox/", views.inbox_view),
    path("api/authors/<path:author_serial>/inbox/", views.inbox_view, name="author-inbox"),
    path("api/authors/<str:author_uuid>/", SingleAuthorAPIView.as_view(), name="api-author-detail"),  
    path("api/authors/", AuthorsListView.as_view(), name="api-authors-list"), 
    path("api/authors/<path:author_serial>/entries/<path:entry_serial>/images/", EntryImageAPIView.as_view(), name="author-entry-images"),
    path("api/Entry/<path:entry_id>/images/", EntryImageAPIView.as_view(), name="author-entry-images-cap"),
    path("api/EntryImage/<path:id>/", EntryImageAPIView.as_view(), name="get-entry-image-cap"),

    path("friends/", views.friends, name="friends"),
    path('add_comment/', views.add_comment, name = "add_comment"),
    path('add_like/', views.toggle_like, name='add_like'),
    path("node_admin/", views.profile_view, name="node_admin"), 
    path("api/entries/", EntryAPIView.as_view(), name="api-entries-list"),
]
    