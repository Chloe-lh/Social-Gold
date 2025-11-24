from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

# API view imports (use the modules under golden.api)
from .api.profileAPIView import ProfileAPIView
from .api.nodeAPIView import NodeAPIView
from .api.friendsAPIView import AuthorFriendsView, FollowAPIView
from .api.entryAPIView import EntryAPIView, EntryImageAPIView, ReadingAPIView
from .api.commentAPIView import EntryCommentAPIView, SingleCommentAPIView
from .api.likeAPIView import LikeAPIView, CommentLikeAPIView
from .api.authorsAPIView import AuthorsListView, SingleAuthorAPIView

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
    path('profile/follow/', views.api_follow_action, name="follow-action"),
    path('profile/unfollow/', views.api_unfollow_action, name="unfollow-action"), 

    # API Endpoints
    path("api/authors/", AuthorsListView.as_view(), name="api-authors-list"), 
    path("api/authors/<str:author_uuid>/", SingleAuthorAPIView.as_view(), name="api-author-detail"),  
    path("api/reading/", ReadingAPIView.as_view(), name="api-reading"), 
    path("api/Profile/<path:id>/", ProfileAPIView.as_view(), name="get-profile"),
    path("api/Node/<path:id>/", NodeAPIView.as_view(), name="get-node"),
    path("api/Follow/<path:id>/", FollowAPIView.as_view(), name="get-follow"),
    path("api/Author/<path:author_id>/friends/", AuthorFriendsView.as_view()),
    path("api/Like/<path:id>/", LikeAPIView.as_view(), name="get-like"),

    # Entry-related API
    path("api/Entry/<path:entry_id>/comments/", EntryCommentAPIView.as_view(), name="entry-comments-alias"),
    path("api/Entry/<path:id>/", EntryAPIView.as_view(), name="get-entry"),
    # --------------------------- COMMENTS ---------------------------------
    # Accept full-FQID inbox POSTs (remote POST)
    # i just commented thiss line out bcoz it was interfering with the inbox view for all other stuff
    #path("api/authors/<path:author_serial>/inbox/", InboxView.as_view(), name="inbox-accept-fullfqid"),
    # Author-nested alias for getting comments on an entry from a certain author
    # supports POST and GET

    # Follow-related API Endpoints
    path("api/Follow/<path:author_id>/request/", views.api_follow_requests, name="api-follow-request"),
    path("api/Follow/<path:author_id>/unfollow/", views.api_unfollow_action, name="api-unfollow"),

    # Comments
    path("api/authors/<path:author_serial>/entries/<path:entry_serial>/comments/", EntryCommentAPIView.as_view(), name="author-entry-comments"),
    # get comments on entry that server knows about
    # list comments using entry's global id
    path("api/entries/<path:entry_fqid>/comments/", EntryCommentAPIView.as_view(), name="list-comments-full-fqid"),
    # Backwards-compatible entry-centric route (tests and some clients expect /api/Entry/ID/comments/)
    path("api/entry/<path:entry_id>/comments/", EntryCommentAPIView.as_view(), name="entry-comments"),
    # Backwards-compatible alias with capital 'Entry' used by some clients/tests
    path("api/Entry/<path:entry_id>/comments/", EntryCommentAPIView.as_view(), name="entry-comments-alias"),
    # generic Entry route should come after comment-specific routes so the
    # '/comments/' suffix is matched by the comment view rather than being
    # captured as part of the Entry id by the generic route.
    # get a single comment by id
    path("api/authors/<str:author_id>/entries/<str:entry_id>/comments/<path:comment_fqid>/", SingleCommentAPIView.as_view()),
    # # --------------------------- LIKES ------------------------------------
    path("api/authors/<path:author_serial>/entries/<path:entry_serial>/likes/", LikeAPIView.as_view(), name="author-entry-likes"),
    path("api/entries/<path:entry_fqid>/likes/", LikeAPIView.as_view(), name="entry-likes"),
    path("api/Entry/<path:entry_id>/likes/", LikeAPIView.as_view(), name="entry-likes-alias"),
    path("api/Comment/<path:comment_id>/likes/", CommentLikeAPIView.as_view(), name="comment-likes"),
    # ------------------------------------------------------------------------
    # ! Thee two serve the same purpose, but the first is for getting images, the second is for uploading images to an entry
    path("api/EntryImage/<int:id>/", EntryImageAPIView.as_view(), name="get-entry-image"),
    path("api/Entry/<path:entry_id>/images/", EntryImageAPIView.as_view(), name="entryimage-upload"),

    #path("api/author/<uuid:author_id>/inbox/", views.inbox, name="inbox"),
    #path('api/authors/<uuid:author_id>/followers/accept/', views.accept_follow, name='accept_follow'),
    #path('api/authors/<uuid:author_id>/followers/reject/', views.reject_follow, name='reject_follow'),
    #path("api/entries/<uuid:entry_id>/", views.handle_update, name="entry_update"),
    #path('api/authors/', views.remote_authors_list, name='remote-authors-list'),
    path("api/authors/<uuid:author_id>/inbox/", views.inbox_view, name="author-inbox"),

    path("friends/", views.friends, name="friends"),
    path('add_comment/', views.add_comment, name = "add_comment"),
    path('add_like/', views.toggle_like, name='add_like'),
    path("node_admin/", views.profile_view, name="node_admin"), 
    path("api/entries/", EntryAPIView.as_view(), name="api-entries-list")
]
    