from django.urls import path
from django.contrib.auth import views as auth_views
from . import apiViews, views

from .apiViews import EntryImageAPIView, AuthorFriendsView
from .api.commentAPIView import EntryCommentAPIView, SingleCommentAPIView
from .api.likeAPIView import LikeAPIView

'''
These URL Patterns registers all views 
'''
urlpatterns = [
    path("", views.stream_view, name="stream"),
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
    path('stream/', views.stream_view, name="stream-link"),
    # TODO: change the id to be the id, whatever we decide to use later
    # TODO: entries can have comment page number queries (Or we just allow infinite scroll for comments..?)
    # TODO: entries should have comments feature if there is a logged in user

    # TODO: the following may be deleted/incorporated into another view
    path("friends/", views.friends, name="friends"),
    path('add_comment/', views.add_comment, name = "add_comment"),
    path('add_like/', views.toggle_like, name='add_like'), # temporary
    path("node_admin/", views.profile_view, name="node_admin"), # You need to change the views.new_post to the actual admin view when it's created 

    # API end points
    # API views will be visible in /swagger/
    # Switched from <str:id> to <path:id> for file and URL flexibility
    path("api/Profile/<path:id>/", apiViews.ProfileAPIView.as_view(), name="get-profile"),
    path("api/Node/<path:id>/", apiViews.NodeAPIView.as_view(), name="get-node"),
    path("api/Follow/<path:id>/", apiViews.FollowAPIView.as_view(), name="get-follow"),
    path("api/Author/<path:author_id>/friends/", AuthorFriendsView.as_view()),
    path("api/Like/<path:id>/", LikeAPIView.as_view(), name="get-like"),
    path("api/Entry/<path:id>/", apiViews.EntryAPIView.as_view(), name="get-entry"),

    # --------------------------- COMMENTS ---------------------------
    # Accept full-FQID inbox POSTs (remote POST)
    path("api/authors/<path:author_serial>/inbox/", apiViews.InboxView.as_view(), name="inbox-accept-fullfqid"),
    # Author-nested alias for getting comments on an entry from a certain author
    # supports POST and GET
    path("api/authors/<path:author_serial>/entries/<path:entry_serial>/comments/", EntryCommentAPIView.as_view(), name="author-entry-comments"),
    # get comments on entry that server knows about
    # list comments using entry's global id
    path("api/entries/<path:entry_fqid>/comments/", EntryCommentAPIView.as_view(), name="list-comments-full-fqid"),
    # Backwards-compatible entry-centric route (tests and some clients expect /api/Entry/ID/comments/)
    path("api/entry/<path:entry_id>/comments/", EntryCommentAPIView.as_view(), name="entry-comments"),
    # get a single comment by id
    path("api/authors/<str:author_id>/entries/<str:entry_id>/comments/<path:comment_fqid>/", SingleCommentAPIView.as_view()),
    # # --------------------------- COMMENTED ----------------------------
    # path("api/authors/<path:author_serial>/commented", apiViews.CommentedAPIView.as_view(), name="commented"),
    # # list of comments the author authored
    # path("api/authors/<path:author_id>/commented/", apiViews.AuthorCommentedAPIView.as_view(), name="author-commented"),

    # ! Thee two serve the same purpose, but the first is for getting images, the second is for uploading images to an entry
    path("api/EntryImage/<int:id>/", apiViews.EntryImageAPIView.as_view(), name="get-entry-image"),
    path("api/Entry/<path:entry_id>/images/", EntryImageAPIView.as_view(), name="entryimage-upload"),

    path("api/author/<uuid:author_id>/inbox/", views.inbox, name="inbox"),
    path('api/authors/<uuid:author_id>/followers/accept/', views.accept_follow, name='accept_follow'),
    path('api/authors/<uuid:author_id>/followers/reject/', views.reject_follow, name='reject_follow'),
    path("api/entries/<uuid:entry_id>/", views.handle_update, name="entry_update"),
]
    

