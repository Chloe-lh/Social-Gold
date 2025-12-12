from django.db import models
from django.utils import timezone
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.postgres.fields import JSONField 
from django.conf import settings
import uuid

"""
Relationship Summary 

AUTHOR
Author 1 ────> * Entries (Entry.author FK -> Author)
Author 1 ────> * Comments (Comment.author FK -> Author)
Author 1 ────> * LikesCreated (Like.author FK -> Author)
Author 1 ────> * FollowsSent (Follow.actor FK -> Author)
Author 1 ────> * InboxItems (Inbox.author FK -> Author)
Author <────> Author (Asymmetrical M2M -> following; mutual = friends)
Authors * <────> * Nodes (Node.admins M2M -> Author)

ENTRY
Entry * <──── 1 Author (Entry.author FK -> Author)
Entry 1 ────> * Comments (Comment.entry FK -> Entry)
Entry 1 ────> * Images (EntryImage.entry FK -> Entry)
Entry * <────> * Authors (Entry.likes M2M -> Author)

COMMENT
Comment * <──── 1 Author(Comment.author FK -> Author)
Comment * <──── 1 Entry (Comment.entry FK -> Entry)
Comment 1 ────> * Replies (Comment.reply_to self-FK)
Comment * <────> * Authors (Comment.likes M2M -> Author)

LIKE
Like * <──── 1 Author (Like.author FK -> Author)
Like → Object (Stored as URL, not FK) (For entries and comments)

FOLLOW
Follow * <──── 1 Author (Follow.actor FK -> Author)
Follow -> TargetAuthor (Stored as URL, not FK)

INBOX
Inbox * <──── 1 Author (Inbox.author FK -> Author)

NODE
Node * <────> * Authors (Node.admins M2M -> Author)
Node 1 ────> * KnownNodes (KnownNode.parent FK -> Node)

KNOWNNODE
KnownNode * <──── 1 Node (KnownNode.parent FK -> Node)
""" 

VISIBILITY_CHOICES = [
    ("PUBLIC", "Public"),
    ("UNLISTED", "Unlisted"),
    ("FRIENDS", "Friends-Only"),
    ("DELETED", "Deleted"),
]

FOLLOW_STATE_CHOICES = [
    ("REQUESTED", "requested"),
    ("ACCEPTED", "accepted"),
    ("REJECTED", "rejected"),
]

class MyUserManager(BaseUserManager):

    def _generate_fqid(self):
        return f"{settings.SITE_URL}/api/authors/{uuid.uuid4()}"

    def create_user(self, username, email=None, password=None, **extra_fields):
        if not email:
            raise ValueError("Email required")
        if not username:
            raise ValueError("Username required")
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.id = self._generate_fqid()
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_admin", True)
        extra_fields.setdefault("is_approved", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(username, email, password, **extra_fields)

class Author(AbstractBaseUser, PermissionsMixin):
    id = models.URLField(primary_key=True, unique = True)
    host  = models.URLField(blank=True)
    github = models.URLField(blank=True)
    web = models.URLField(blank=True)
    profileImage = models.ImageField(
        default="profile_pics/default_profile.png",
        upload_to='profile_pics/')
    username = models.CharField(max_length=50, unique=True, default="goldenuser")
    password = models.CharField(max_length=128, default="goldenpassword")
    name = models.CharField(max_length=100, blank=True) # is this going to stay as name or will be displayName? 
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
    friends = property(lambda self: self.following.filter(id__in=self.followers_set.values_list("id", flat=True)))
    objects = MyUserManager()
    description = models.TextField(blank=True)
    #is_shadow = models.BooleanField(default=False)
    #is_local = models.BooleanField(default=True)

    # Authentication Requirements 
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

    def update_friends(self):
        """
        Updates the `friends` JSONField to contain mutual followers.
        Keys = friend's FQID, Values = info (username, etc)
        """
        return self.friends

    def save(self, *args, **kwargs):
        if not self.id:
            self.id = f"{settings.SITE_URL}/api/authors/{uuid.uuid4()}"
        if not self.host:
            # Set host to SITE_URL automatically
            self.host = settings.SITE_URL.rstrip('/')  # remove trailing slash just in case
        super().save(*args, **kwargs)

    @property
    def uuid_only(self):
        return self.id.rstrip("/").split("/")[-1]
    
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
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='PUBLIC', db_index=True)
    published = models.DateTimeField(auto_now_add=True) # auto_now_add=True means it is only set ONCE on creation.

    # auto_now_add=True means it is only set ONCE on creation.
    is_posted = models.DateTimeField(default=timezone.now)
    is_updated = models.DateTimeField(auto_now=True)

    # We use URLs for authors to support remote likes and comments from different nodes.
    # stores a list of authors that liked and entry
    likes = models.ManyToManyField(
        'Author',
        related_name='liked_entries',
        blank=True
    )
    # comments = models.ManyToManyField(
    #     'Author',
    #     related_name='comments',
    #     blank = True
    # )
    # String representation for admin/debugging.
    def __str__(self):
        return f"Entry by {self.author} ({self.visibility})"

    def get_uuid(self):
        """Return the UUID suffix from the entry's FQID `id`.

        Templates call `entry.get_uuid` to build local URLs (the URLconf
        uses a `<uuid:entry_uuid>` segment). If `id` is empty or does not
        contain slashes, return an empty string to avoid broken reverses.
        """
        if not self.id:
            return ""
        try:
            return str(self.id).rstrip('/').split('/')[-1]
        except Exception:
            return ""
    
    def get_all_images(self):
        """
        Get all images for this entry, including:
        1. Local EntryImage objects (for local entries)
        2. Images extracted from HTML content (for remote entries)
        Returns a list of image URLs.
        """
        image_urls = []
        
        # First, add images from EntryImage objects (local entries)
        for img in self.images.all():
            image_url = img.image.url
            # Make absolute URL if relative
            if image_url.startswith('/'):
                from django.conf import settings
                image_url = f"{settings.SITE_URL.rstrip('/')}{image_url}"
            image_urls.append(image_url)
        
        # If no EntryImage objects, extract images from HTML content (remote entries)
        if not image_urls and self.content:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.content, 'html.parser')
            img_tags = soup.find_all('img')
            for img_tag in img_tags:
                img_src = img_tag.get('src')
                if img_src:
                    # Skip data URLs
                    if img_src.startswith('data:'):
                        continue
                    # Make absolute if relative
                    if img_src.startswith('/'):
                        from django.conf import settings
                        img_src = f"{settings.SITE_URL.rstrip('/')}{img_src}"
                    elif not img_src.startswith('http'):
                        # Relative URL without leading slash
                        from django.conf import settings
                        img_src = f"{settings.SITE_URL.rstrip('/')}/{img_src}"
                    image_urls.append(img_src)
        
        return image_urls

class EntryImage(models.Model):
    """
    Multiple images can be associated with a single Entry.
    Access via: entry.images.all()
    """
    id = models.URLField(primary_key=True, unique=True)
    entry = models.ForeignKey(
        Entry,
        on_delete=models.CASCADE,
        related_name='images',
        blank = True,
        null = True
        
    )
    name = models.CharField(max_length=255, blank=True, null=True)
    image = models.ImageField(upload_to='entry_images/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    order = models.PositiveIntegerField(default=0)  
    
    class Meta:
        ordering = ['order', 'uploaded_at']
    
    def __str__(self):
        if self.entry:
            return f"Image for entry {self.entry.id}"
        return f"Standalone Image {self.id}"  # or just "Standalone Image"
    
    @property
    def url(self):
        return self.image.url
    
class Comment(models.Model):
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
        related_name="comment"
    )
    entry = models.ForeignKey(
        Entry,
        to_field='id',
        db_column='entry_id',
        on_delete=models.CASCADE, 
        related_name="comment"
    )
    content = models.TextField(max_length=200, blank=True)
    contentType = models.CharField(max_length=100, default="text/markdown")
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    published = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(
        'Author',
        related_name='liked_comments',
        blank=True
    )
    def like_count(self):
        return Like.objects.filter(object=self.id).count()

'''
Another person create their own node by setting up their own server and running our Django project
as a separate instance. They get a unique url that they should add to their node info
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

    # for checking for online nodes
    is_active = models.BooleanField(default=False)

    # Remote nodes this node knows about & can communicate with
    # remote_nodes = models.JSONField(default=list, blank=True)
    # Later this could become its own table for more features

class KnownNode(models.Model):
    parent = models.ForeignKey(Node, related_name="known_nodes", on_delete=models.CASCADE)
    url = models.URLField()

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
    object = models.URLField(db_index=True)
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
        related_name='outgoing_follow_requests',
        db_index=True
    )
    object = models.URLField()  # FQID of the author being followed
    state = models.CharField(max_length=20, choices=FOLLOW_STATE_CHOICES, default="REQUESTING", db_index=True)
    published = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Follow {self.id} {self.actor} -> {self.object} ({self.state})"

class Inbox(models.Model):
    """
    Represents an ActivityPub inbox for a given author.
    Stores activities received by that author.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name="inbox_items"
    )
    data = models.JSONField()  # Raw activity JSON
    received_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-received_at']