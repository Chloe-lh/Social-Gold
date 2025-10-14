from django.db import models

# Create your models here.

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
    pass

class Comments(models.Model):

    post = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="comments")
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    comment_string = models.TextField()
    likes = models.ManyToManyField(Author, blank=True, related_name='liked_comments')
    posted = models.DateTimeField(auto_now_add=True)


class Node(models.Model):
    pass