from django.db import models

# Create your models here.
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

class Author(models.Model):
    id = models.AutoField(primary_key=True)
    userName = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=20)
    is_admin = models.BooleanField(default=False)
    following = models.ManyToManyField('self', symmetrical=False, related_name='followers_set', blank=True)
    followers_info = models.JSONField(default=dict, blank=True)


    def __str__(self):
        return self.username

class Entry(models.Model):
    # We use a FULL URL (FQID) as the primary key instead of an integer.
    # This ensures posts can be uniquely identified across multiple nodes/servers in federation.
    # Example: https://node1.com/api/entries/123
    id = models.URLField(primary_key=True, unique=True) # FQID

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
    
    # We store a string like 'PUBLIC', but display a readable version in admin/UI.
    VISIBILITY_CHOICES = [
        ('PUBLIC', 'Public'),
        ('UNLISTED', 'Unlisted'),
        ('FRIENDS', 'Friends-Only'),
        ('DELETED', 'Deleted'),
    ]
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='PUBLIC')
    
    # auto_now_add=True means it is only set ONCE on creation.
    posted = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # We use URLs for authors to support remote likes from different nodes.
    likes = models.ManyToManyField(
        'Author',
        related_name='liked_entries',
        blank=True
    )

    # String representation for admin/debugging.
    def __str__(self):
        return f"Entry by {self.author} ({self.visibility})"

class Comments(models.Model):

    post = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="comments")
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    comment_string = models.TextField()
    likes = models.ManyToManyField(Author, blank=True, related_name='liked_comments')
    posted = models.DateTimeField(auto_now_add=True)


class Node(models.Model):
    '''
    id: string (URL or hostname)
    title: string
    description: string
    admins: Array<AuthorID>
    remote_nodes: Array<URL>
    '''
    pass