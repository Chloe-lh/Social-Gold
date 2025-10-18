from django.test import TestCase
from django.core.exceptions import ValidationError
from .models import Author, Entry, Comments, Node, Like, Follow
from django.utils import timezone
from urllib.parse import urlparse

class ModelTests(TestCase):

    def setUp(self):
        # Create a node
        self.node = Node.objects.create(id="https://node.example.com", title="Test Node")
        
        # Create two authors
        self.author1 = Author.objects.create(
            id="https://node.example.com/api/authors/1",
            userName="alice",
            password="pass123",
            host=self.node.id
        )
        self.author2 = Author.objects.create(
            id="https://node.example.com/api/authors/2",
            userName="bob",
            password="pass123",
            host=self.node.id
        )
        
        # Author1 follows Author2
        self.author1.following.add(self.author2)

        # Create an entry
        self.entry = Entry.objects.create(
            id="https://node.example.com/api/authors/1/entries/100",
            author=self.author1,
            title="Hello World",
            content="This is my first entry",
            visibility="PUBLIC"
        )

        # Create a comment
        self.comment = Comments.objects.create(
            id="https://node.example.com/api/authors/2/comments/200",
            author=self.author2,
            entry=self.entry,
            comment="Nice post!"
        )

        # Create a like
        self.like = Like.objects.create(
            id="https://node.example.com/api/authors/2/likes/300",
            author=self.author2,
            object=self.entry.id,
            published=timezone.now()
        )

        # Create a follow request
        self.follow = Follow.objects.create(
            id="https://node.example.com/api/authors/2/follow/400",
            actor=self.author2,
            object=self.author1.id,
            state="REQUESTING",
            published=timezone.now()
        )

    def test_author_creation(self):
        self.assertEqual(self.author1.userName, "alice")
        self.assertTrue(self.author1.id.startswith("http"))

    def test_author_following(self):
        self.assertIn(self.author2, self.author1.following.all())
        self.assertIn(self.author1, self.author2.followers_set.all())

    def test_entry_creation(self):
        self.assertEqual(self.entry.author, self.author1)
        self.assertEqual(self.entry.visibility, "PUBLIC")
        self.assertTrue(urlparse(self.entry.id).scheme.startswith("http"))

    def test_comment_creation(self):
        self.assertEqual(self.comment.entry, self.entry)
        self.assertEqual(self.comment.author, self.author2)

    def test_like_creation(self):
        self.assertEqual(self.like.object, self.entry.id)
        self.assertEqual(self.like.author, self.author2)

    def test_follow_creation(self):
        self.assertEqual(self.follow.actor, self.author2)
        self.assertEqual(self.follow.object, self.author1.id)
        self.assertEqual(self.follow.state, "REQUESTING")

    def test_entry_edit(self):
        self.entry.content = "Updated content"
        self.entry.save()
        updated_entry = Entry.objects.get(id=self.entry.id)
        self.assertEqual(updated_entry.content, "Updated content")

    def test_comment_reply(self):
        reply = Comments.objects.create(
            id="https://node.example.com/api/authors/1/comments/201",
            author=self.author1,
            entry=self.entry,
            reply_to=self.comment,
            comment="Thanks!"
        )
        self.assertEqual(reply.reply_to, self.comment)
        self.assertIn(reply, self.comment.replies.all())
