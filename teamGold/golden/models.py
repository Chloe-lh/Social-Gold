from django.db import models

# Create your models here.
'''
Relationship Summary
Author 1 ────> * Entry             # One author can create many entries
Author 1 ────> * Comment           # One author can create many comments
Entry  1 ────> * Comment           # One entry can have many comments
Entry  *  ────< * Author (Like)    # Many authors can like many entries via Like objects
Comment *  ────< * Author (Like)   # Many authors can like many comments via Like objects
Author *  ────< * Author (Followers/Following)  # Self-referential M2M for followers/following
Node   1  ────> * Author           # One node can host many authors

Note: When building a federated social platform, each object must
have a fully qualified URL (FQID) that includes the nodes domain
'''

VISIBILITY_CHOICES = [
    ("PUBLIC", "Public"),
    ("UNLISTED", "Unlisted"),
    ("FRIENDS", "Friends-Only"),
    ("DELETED", "Deleted"),
]

FOLLOW_STATE_CHOICES = [
    ("REQUESTING", "requesting"),
    ("ACCEPTED", "accepted"),
    ("REJECTED", "rejected"),
]

class Author(models.Model):
    """
    Author object matching spec. Public identity MUST be the full API URL.
    Example id: "http://nodeaaaa/api/authors/111"
    """
    id = models.URLField(primary_key=True, unique=True)
    host  = models.URLField(blank=True)
    github = models.URLField(blank=True)
    web = models.URLField(blank=True)
    profileImage = models.URLField(blank=True)
    userName = models.CharField(max_length=100, unique=True, default="temp_user")
    password = models.CharField(max_length=20,  default="temp_pass")
    is_admin = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    following = models.ManyToManyField(
        'self', symmetrical=False, 
        related_name='followers_set', 
        blank=True)
    followers_info = models.JSONField(default=dict, blank=True)


    def __str__(self):
        return self.userName

class Entry(models.Model):
    """
    Entry (single post) object. ID is the FQID on the original node.
    Example id: "http://nodebbbb/api/authors/222/entries/249"
    """
    id = models.URLField(primary_key=True, unique=True) # FQID
    type = models.CharField(max_length=20, default="entry", editable=False)
    title = models.CharField(max_length=300, blank=True)
    web = models.URLField(blank=True)
    description = models.TextField(blank=True)
    contentType = models.CharField(max_length=100, default="text/plain")
    content = models.TextField()  # Can be text, markdown, or even a URL pointing to an image.
    author = models.ForeignKey( # Author is linked using their FULL URL (id field on Author).
        'Author',
        to_field='id', # to_field='id' ensures Django joins based on the author's URL and not a numeric key.
        db_column='author_id', # db_column='author_id' sets the actual column name in the database.
        on_delete=models.CASCADE,
        related_name='entries'       
    )
    source = models.URLField(blank=True)     # where the content was originally published (HTML)
    origin = models.URLField(blank=True)     # original node that created the entry
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='PUBLIC')
    published = models.DateTimeField(auto_now_add=True) # auto_now_add=True means it is only set ONCE on creation.

    # String representation for admin/debugging.
    def __str__(self):
        return f"Entry by {self.author} ({self.visibility})"

class Comments(models.Model):
    """
    Comment object (federated). ID is the FQID of the comment.
    Example id: "http://nodeaaaa/api/authors/111/commented/130"
    """
    id = models.URLField(primary_key=True, unique=True)  # FQID
    type = models.CharField(max_length=20, default="comment", editable=False)
    author = models.ForeignKey(
        Author, 
        to_field='id',
        db_column='author_id',
        on_delete=models.CASCADE, 
        related_name="comments"
    )
    entry = models.ForeignKey(
        Entry,
        to_field='id',
        db_column='entry_id',
        on_delete=models.CASCADE, 
        related_name="comments"
    )
    contentType = models.CharField(max_length=100, default="text/markdown")
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    comment = models.TextField()
    published = models.DateTimeField(auto_now_add=True)

class Node(models.Model):
    """
    Represents a remote or local node / server.
    remote node : other servers/seperate instances of app
    id: full URL of node (e.g. https://node.example)
    remote_nodes: JSON list of known node URLs (optional)
    """
     # The unique URL or hostname of this node
    id = models.URLField(primary_key=True)   # ie. "https://social.example.com"

    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    # this allows for HTTP Authentication
    auth_user = models.CharField(max_length=100)
    auth_pass = models.CharField(max_length=100)

    # Who administrates this node (local admins)
    admins = models.ManyToManyField(
        'Author',
        related_name="admin_of_nodes",
        blank=True
    )

    # Remote nodes this node knows about & can communicate with
    remote_nodes = models.JSONField(default=list, blank=True)
    # Later this could become its own table for more features

    def __str__(self):
        return self.title

class Like(models.Model):
    """
    Like object as an independent activity.
    Example id: "http://nodeaaaa/api/authors/111/liked/166"
    Stores the actor (author who liked), the object (FQID of liked object),
    and published timestamp.
    """
    id = models.URLField(primary_key=True, unique=True)  # FQID
    type = models.CharField(max_length=20, default="like", editable=False)
    author = models.ForeignKey(
        Author,
        to_field='id',
        db_column='author_id',
        on_delete=models.CASCADE,
        related_name='likes'   # likes authored by this author
    )
    # the full FQID of the object liked (entry or comment or other)
    object = models.URLField()
    published = models.DateTimeField()

    def __str__(self):
        return f"Like {self.id} by {self.author.displayName or self.author.id} -> {self.object}"

class Follow(models.Model):
    """
    Follow / follow-request activity object.
    ID is the FQID of the follow activity.
    actor -> object (both are Author FQIDs in most cases)
    state indicates whether the follow request is requesting/accepted/rejected.
    """
    id = models.URLField(primary_key=True, unique=True)  # FQID
    type = models.CharField(max_length=20, default="follow", editable=False)
    summary = models.CharField(max_length=500, blank=True)
    actor = models.ForeignKey(
        Author,
        to_field='id',
        db_column='actor_id',
        on_delete=models.CASCADE,
        related_name='outgoing_follow_requests'
    )
    object = models.URLField()  # FQID of the author being followed
    state = models.CharField(max_length=20, choices=FOLLOW_STATE_CHOICES, default="REQUESTING")
    published = models.DateTimeField()

    def __str__(self):
        return f"Follow {self.id} {self.actor} -> {self.object} ({self.state})"