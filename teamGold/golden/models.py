from django.db import models
from django.utils import timezone
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager

'''
Relationship Summary
Author 1 ────> * Entry
Author 1 ────> * Comment
Entry  1  ────> * Comment
Entry  *  ────< * Author (Likes)
Comment *  ────< * Author (Likes)
Author *  ────< * Author (Followers/Following)
Node   1  ────> * Author

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

class MyUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_admin", True)
        extra_fields.setdefault("is_approved", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)

class Author(AbstractBaseUser, PermissionsMixin):
    id = models.URLField(primary_key=True)
    host  = models.URLField(blank=True)
    github = models.URLField(blank=True)
    web = models.URLField(blank=True)
    profileImage = models.URLField(default="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQBkA9WO3FnL4fddebhCcTztCr6vr2METdo9w&s")
    username = models.CharField(max_length=50, unique=True, default="goldenuser")
    password = models.CharField(max_length=50, default="goldenpassword")
    email = models.CharField(blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    is_admin = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    following = models.ManyToManyField(
        'self', symmetrical=False, 
        related_name='followers_set', 
        blank=True)
    followers_info = models.JSONField(default=dict, blank=True)
    objects = MyUserManager()

    # Authentication
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username
    
    @classmethod
    def from_user(cls, user):
        """
        Return the Author instance for a Django auth user, or None if not found.
        """
        if not getattr(user, "is_authenticated", False):
            return None
        try:
            return cls.objects.get(username=user.username) # matching via username 
        except cls.DoesNotExist:
            return None

class Entry(models.Model):
    """
    This class is using a FULL URL (FQID) as the primary key instead of an integer.
    This decision ensures entries can be uniquely identified across multiple nodes. 
    Example: https://node1.com/api/entries/123
    """

    id = models.URLField(primary_key=True, unique=True) # FQID
    type = models.CharField(max_length=20, default="entry", editable=False)
    title = models.CharField(max_length=300, blank=True)
    web = models.URLField(blank=True)
    description = models.TextField(blank=True)
    contentType = models.CharField(max_length=100, default="text/plain")
    # image = models.ImageField(upload_to='entry_images/', blank=True, null=True) # pip install pillow is required so yes, download new
    # Author is linked using their FULL URL (id field on Author).
    # to_field='id' ensures Django joins based on the author's URL and not a numeric key.
    # db_column='author_id' sets the actual column name in the database.
    author = models.ForeignKey(
        'Author',
        to_field='id',
        db_column='author_id',
        on_delete=models.CASCADE,
        related_name='entries'       
    )
    content = models.TextField()  # Can be text, markdown, or even a URL pointing to an image.
    source = models.URLField(blank=True)     # where the content was originally published (HTML)
    origin = models.URLField(blank=True)     # original node that created the entry

    # We store a string like 'PUBLIC', but display a readable version in admin/UI.
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='PUBLIC')
    published = models.DateTimeField(auto_now_add=True) # auto_now_add=True means it is only set ONCE on creation.

    # auto_now_add=True means it is only set ONCE on creation.
    is_posted = models.DateTimeField(default=timezone.now)
    is_updated = models.DateTimeField(auto_now=True)

    # We use URLs for authors to support remote likes from different nodes.
    likes = models.ManyToManyField(
        'Author',
        related_name='liked_entries',
        blank=True
    )

    # String representation for admin/debugging.
    def __str__(self):
        return f"Entry by {self.author} ({self.visibility})"

class EntryImage(models.Model):
    """
    Multiple images can be associated with a single Entry.
    Access via: entry.images.all()
    """
    entry = models.ForeignKey(
        Entry,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='entry_images/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    order = models.PositiveIntegerField(default=0)  
    
    class Meta:
        ordering = ['order', 'uploaded_at']
    
    def __str__(self):
        return f"Image for entry {self.entry.id}"
    

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

'''
Another person create their own node by setting up their own server and running our Django project
as a seperate instance. They get a unique url that they should add to their node info
- the nodes interact by sending HTTP request to API end points (ei /api/authors/)
- example: when another nodes author likes an entry, the remote node sends a API request to
    /api/likes. The local node receives the request and adds the like to the post
'''
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
    auth_user = models.CharField(max_length=100, blank=True, null=True)
    auth_pass = models.CharField(max_length=100, blank=True, null=True)

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
        return f"Like {self.id} by {self.author.username or self.author.id} -> {self.object}"

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
