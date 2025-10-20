'''
Run with: python manage.py test

Caveats Before Running (on new environments)
- pip install django
- pip install whitenoise 
- pip install pillow 
- rm db.sqlite3
- python manage.py makemigrations
- python manage.py migrate 
'''

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from base64 import b64encode
import uuid, tempfile, io, shutil

from golden.models import Author, Entry, EntryImage, Node, Like, Comments, Follow

'''
This module contains comprehensive tests for all GET endpoints of the API, verifying 
that the system correctly retrieves resources by their fully qualified IDs (FQIDs).

Tested endpoints include:

- /api/Profile/<id>/ which retrieves author profiles.
- /api/Entry/<id>/ which retrieves entries/posts.
- /api/Node/<id>/ which retrieves nodes/servers.
- /api/Follow/<id> which retrieves follow/follow-request activities.
- /api/Like/<id>/ which retrieves like activities.
- /api/Comment/<id>/ which retrieves comments on entries.
- /api/EntryImage/<id>/ which retrieves images associated with entries.

Overall, each test class ensures the validity of:
1. Valid resource IDs to return a 200 OK with the correct data.
2. Invalid resource IDs return a 404 Not Found.

This suite supports automated testing for RESTful API compliance and interoperability 
with other nodes, as well as a basic model class.
'''

#===============================
# Helper Functions
#===============================

def make_fqid(base="https://node1.com", *parts):
    p = "/".join(str(p).strip("/") for p in parts if p is not None)
    return f"{base}/{p}"

def _basic_token(username, password):
    return b64encode(f"{username}:{password}".encode()).decode()

#===============================
# Authenticated Base
#===============================

class AuthenticatedAPITestCase(APITestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

        AuthUser = get_user_model()
        self.apiuser, _ = AuthUser.objects.get_or_create(
            username="apiuser",
            defaults={"is_active": True}
        )
        # We're always checking if the user can be approved
        if hasattr(self.apiuser, "is_approved"):
            self.apiuser.is_approved = True
        self.apiuser.set_password("pass")
        self.apiuser.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Basic {_basic_token('apiuser', 'pass')}")

#===============================
# Mode-Level Test Suite (legacy)
#===============================

class ModelTestSuite(TestCase):
    def setUp(self):
        self.node = Node.objects.create(id="https://node.example.com", title="Test Node")

        self.author1 = Author.objects.create(
            id="https://node.example.com/api/authors/1",
            username="alice",
            host=self.node.id
        )
        self.author2 = Author.objects.create(
            id="https://node.example.com/api/authors/2",
            username="bob",
            host=self.node.id
        )

        self.author1.following.add(self.author2)

        self.entry = Entry.objects.create(
            id="https://node.example.com/api/authors/1/entries/100",
            author=self.author1,
            title="Hello World",
            content="This is my first entry",
            visibility="PUBLIC"
        )

        self.comment = Comments.objects.create(
            id="https://node.example.com/api/authors/2/comments/200",
            author=self.author2,
            entry=self.entry,
            comment="Nice post!"
        )

        self.like = Like.objects.create(
            id="https://node.example.com/api/authors/2/likes/300",
            author=self.author2,
            object=self.entry.id,
            published=timezone.now()
        )

        self.follow = Follow.objects.create(
            id="https://node.example.com/api/authors/2/follow/400",
            actor=self.author2,
            object=self.author1.id,
            state="REQUESTING",
            published=timezone.now()
        )

    def test_author_unaccepted(self):
        # default False unless your model sets otherwise
        self.assertFalse(self.author1.is_approved)

    def test_author_accepted(self):
        self.author2.is_approved = True
        self.author2.save()
        self.author2.refresh_from_db()
        self.assertTrue(self.author2.is_approved)

    def test_author_creation(self):
        self.assertEqual(self.author1.username, "alice")
        self.assertTrue(self.author1.id.startswith("http"))

    def test_author_following(self):
        self.assertIn(self.author2, self.author1.following.all())
        self.assertIn(self.author1, self.author2.followers_set.all())

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

#===============================
# API Test Suite
#===============================

class BasicAuthBehaviorTestSuite(APITestCase):
    def setUp(self):
        self.client = APIClient()
        from golden.models import Author
        self.author = Author.objects.create(
            id="https://node1.com/api/authors/demo", username="demo", is_approved=True
        )

        User = get_user_model()
        self.apiuser, _ = User.objects.get_or_create(
            username="apiuser",
            defaults={"email": "api@email.com", "is_active": True},
        )
        self.apiuser.set_password("pass")
        if hasattr(self.apiuser, "is_approved"):
            self.apiuser.is_approved = True
        self.apiuser.save()
        
    def test_401_then_200(self):
        # No auth -> 401
        r1 = self.client.get(f"/api/Profile/{self.author.id}/")
        self.assertEqual(r1.status_code, 401)
        self.assertIn("WWW-Authenticate", r1)

        # With basic auth -> 200
        token = b64encode(b"apiuser:pass").decode()
        self.client.credentials(HTTP_AUTHORIZATION=f"Basic {token}")
        r2 = self.client.get(f"/api/Profile/{self.author.id}/")
        self.assertEqual(r2.status_code, 200)

class APITestSuite(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()

        self.author = Author.objects.create(
            id=make_fqid("https://node1.com", "api", "authors", uuid.uuid4()),
            username="testuser",
            email="test@example.com",
            is_approved=True,
        )
        self.entry = Entry.objects.create(
            id=make_fqid("https://node1.com", "api", "entries", uuid.uuid4()),
            author=self.author,
            title="Hello world",
            content="Sample post",
            visibility="PUBLIC",
        )
        self.node = Node.objects.create(
            id="https://node1.com/",
            title="Node One",
            description="Local node",
        )
        self.follow = Follow.objects.create(
            id=make_fqid("https://node1.com", "api", "follows", uuid.uuid4()),
            actor=self.author,
            object=self.author.id,
            state="REQUESTING",
            published=timezone.now(),
        )
        self.like = Like.objects.create(
            id=make_fqid("https://node1.com", "api", "likes", uuid.uuid4()),
            author=self.author,
            object=self.entry.id,
            published=timezone.now(),
        )
        self.comment = Comments.objects.create(
            id=make_fqid("https://node1.com", "api", "comments", uuid.uuid4()),
            author=self.author,
            entry=self.entry,
            comment="Nice!",
            contentType="text/plain",
        )
        self.entry_image = EntryImage.objects.create(
            entry=self.entry, image="entry_images/test_image.jpg", order=0
        )

    def test_get_profile_success_and_404(self):
        r = self.client.get(f"/api/Profile/{self.author.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"].split(";")[0], "application/json")
        self.assertEqual(r.data.get("id"), self.author.id)

        r2 = self.client.get("/api/Profile/https://node1.com/api/authors/invalid/")
        self.assertEqual(r2.status_code, 404)

    def test_get_entry_success_and_404(self):
        r = self.client.get(f"/api/Entry/{self.entry.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("id"), self.entry.id)

        r2 = self.client.get("/api/Entry/https://node1.com/api/entries/missing/")
        self.assertEqual(r2.status_code, 404)

    def test_get_node_success_and_404(self):
        r = self.client.get(f"/api/Node/{self.node.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("id"), self.node.id)

        r2 = self.client.get("/api/Node/https://node1.com/invalid/")
        self.assertEqual(r2.status_code, 404)

    def test_get_follow_success_and_404(self):
        r = self.client.get(f"/api/Follow/{self.follow.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("id"), self.follow.id)

        r2 = self.client.get("/api/Follow/https://node1.com/api/follows/missing/")
        self.assertEqual(r2.status_code, 404)

    def test_get_like_success_and_404(self):
        r = self.client.get(f"/api/Like/{self.like.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("id"), self.like.id)

        r2 = self.client.get("/api/Like/https://node1.com/api/likes/missing/")
        self.assertEqual(r2.status_code, 404)

    def test_get_comment_success_and_404(self):
        r = self.client.get(f"/api/Comment/{self.comment.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("id"), self.comment.id)

        r2 = self.client.get("/api/Comment/https://node1.com/api/comments/missing/")
        self.assertEqual(r2.status_code, 404)

    def test_get_entry_image_success_and_404(self):
        r = self.client.get(f"/api/EntryImage/{self.entry_image.id}/")
        self.assertEqual(r.status_code, 200)

        r2 = self.client.get("/api/EntryImage/999999/")
        self.assertEqual(r2.status_code, 404)

class GetCallsTestSuite(AuthenticatedAPITestCase):
    """
    This test suite verifies GET API 
    """
    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=make_fqid("https://node1.com", "api", "authors", uuid.uuid4()),
            username="flowuser",
            email="flow@example.com",
            is_approved=True,
        )

    def test_story_create_entry_like_comment_then_read_via_api(self):
        entry_id = make_fqid("https://node1.com", "api", "entries", uuid.uuid4())
        entry = Entry.objects.create(
            id=entry_id,
            author=self.author,
            title="Story Post",
            content="Body",
            visibility="PUBLIC",
            contentType="text/plain",
        )

        like_id = make_fqid("https://node1.com", "api", "likes", uuid.uuid4())
        Like.objects.create(
            id=like_id, author=self.author, object=entry.id, published=timezone.now()
        )

        comment_id = make_fqid("https://node1.com", "api", "comments", uuid.uuid4())
        Comments.objects.create(
            id=comment_id,
            author=self.author,
            entry=entry,
            comment="Nice one",
            contentType="text/plain",
        )

        r_entry = self.client.get(f"/api/Entry/{entry.id}/")
        self.assertEqual(r_entry.status_code, 200)
        self.assertEqual(r_entry.data["id"], entry.id)

        r_like = self.client.get(f"/api/Like/{like_id}/")
        self.assertEqual(r_like.status_code, 200)
        self.assertEqual(r_like.data["id"], like_id)

        r_comment = self.client.get(f"/api/Comment/{comment_id}/")
        self.assertEqual(r_comment.status_code, 200)
        self.assertEqual(r_comment.data["id"], comment_id)

    def test_story_follow_request_then_read_via_api(self):
        other = Author.objects.create(
            id=make_fqid("https://node1.com", "api", "authors", uuid.uuid4()),
            username="other",
            email="other@example.com",
            is_approved=True,
        )
        follow_id = make_fqid("https://node1.com", "api", "follows", uuid.uuid4())
        Follow.objects.create(
            id=follow_id,
            actor=self.author,
            object=other.id,
            state="REQUESTING",
            published=timezone.now(),
        )
        r = self.client.get(f"/api/Follow/{follow_id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["id"], follow_id)

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class EntryImageFlowTests(AuthenticatedAPITestCase):
    """
    GET Test Suite specifically for image handelling which uses
    a temporary MEDIA_ROOT so that images and information is not
    polluting our repository.
    """
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls._overridden_settings['MEDIA_ROOT'], ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=make_fqid("https://node1.com", "api", "authors", uuid.uuid4()),
            username="imguser",
            email="img@example.com",
            is_approved=True,
        )
        self.entry = Entry.objects.create(
            id=make_fqid("https://node1.com", "api", "entries", uuid.uuid4()),
            author=self.author,
            title="With image",
            content="Has images",
            visibility="PUBLIC",
            contentType="text/plain",
        )

    def test_upload_images_model_then_verify_api(self):
        image_bytes = io.BytesIO(b"\x47\x49\x46\x38\x39\x61")  # tiny GIF header
        upload = SimpleUploadedFile("tiny.gif", image_bytes.getvalue(), content_type="image/gif")

        img = EntryImage.objects.create(entry=self.entry, image=upload, order=0)
        self.assertTrue(img.id)

        r = self.client.get(f"/api/EntryImage/{img.id}/")
        self.assertEqual(r.status_code, 200)

class VisibilityTestSuite(AuthenticatedAPITestCase):
    """
    Test Suite that validates entry choice visibility 
    """
    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=make_fqid("https://node1.com", "api", "authors", "valuser"),
            username="valuser",
            email="val@example.com",
            is_approved=True,
        )

    def test_visibility_choices_enforced(self):
        e = Entry.objects.create(
            id=make_fqid("https://node1.com", "api", "entries", "v1"),
            author=self.author,
            title="V",
            content="C",
            visibility="PUBLIC",
            contentType="text/plain",
        )
        self.assertEqual(e.visibility, "PUBLIC")
        e.visibility = "NOT_A_CHOICE"
        with self.assertRaises(Exception):
            e.full_clean()

    def test_published_auto_and_update_timestamps(self):
        e = Entry.objects.create(
            id=make_fqid("https://node1.com", "api", "entries", "v2"),
            author=self.author,
            title="T",
            content="C",
            visibility="PUBLIC",
        )
        self.assertIsNotNone(e.published)
        old_updated = e.is_updated
        e.content = "C2"
        e.save()
        self.assertGreaterEqual(e.is_updated, old_updated)

# The Following are GET Classes for each model (legacy)
class GETProfileAPITests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="testuser",
            email="test@example.com",
            is_approved=True
        )

    def test_get_profile_success(self):
        res = self.client.get(f"/api/Profile/{self.author.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["id"], self.author.id)

    def test_get_profile_not_found(self):
        fake_id = "https://node1.com/api/authors/invalid"
        res = self.client.get(f"/api/Profile/{fake_id}/")
        self.assertEqual(res.status_code, 404)

class GETEntryAPITests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="entryauthor",
            email="entry@example.com",
            is_approved=True
        )
        self.entry = Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.author,
            title="Hello world",
            content="Sample post",
            visibility="PUBLIC"
        )

    def test_get_entry_success(self):
        res = self.client.get(f"/api/Entry/{self.entry.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["id"], self.entry.id)

    def test_get_entry_not_found(self):
        fake_id = "https://node1.com/api/entries/invalid"
        res = self.client.get(f"/api/Entry/{fake_id}/")
        self.assertEqual(res.status_code, 404)

class GETNodeAPITests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.node = Node.objects.create(
            id=f"https://node1.com/",
            title="Test Node",
            description="Local test node"
        )

    def test_get_node_success(self):
        res = self.client.get(f"/api/Node/{self.node.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["id"], self.node.id)

    def test_get_node_not_found(self):
        fake_id = "https://node1.com/invalid"
        res = self.client.get(f"/api/Node/{fake_id}/")
        self.assertEqual(res.status_code, 404)

class GETFollowAPITests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.follower = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="follower",
            email="follower@example.com",
            is_approved=True
        )
        self.followed = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="followed",
            email="followed@example.com",
            is_approved=True
        )
        self.follow = Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=self.follower,
            object=self.followed.id,
            state="REQUESTING",
            published=timezone.now()
        )

    def test_get_follow_success(self):
        res = self.client.get(f"/api/Follow/{self.follow.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["id"], self.follow.id)

    def test_get_follow_not_found(self):
        fake_id = "https://node1.com/api/follows/invalid"
        res = self.client.get(f"/api/Follow/{fake_id}/")
        self.assertEqual(res.status_code, 404)

class GETLikeAPITests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="liker",
            email="liker@example.com",
            is_approved=True
        )
        self.entry = Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.author,
            title="Likeable post",
            content="Like me!",
            visibility="PUBLIC"
        )
        self.like = Like.objects.create(
            id=f"https://node1.com/api/likes/{uuid.uuid4()}",
            author=self.author,
            object=self.entry.id,
            published=timezone.now()
        )

    def test_get_like_success(self):
        res = self.client.get(f"/api/Like/{self.like.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["id"], self.like.id)

    def test_get_like_not_found(self):
        fake_id = "https://node1.com/api/likes/invalid"
        res = self.client.get(f"/api/Like/{fake_id}/")
        self.assertEqual(res.status_code, 404)

class GETCommentAPITests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="commenter",
            email="commenter@example.com",
            is_approved=True
        )
        self.entry = Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.author,
            content="Commentable entry",
            visibility="PUBLIC"
        )
        self.comment = Comments.objects.create(
            id=f"https://node1.com/api/comments/{uuid.uuid4()}",
            author=self.author,
            entry=self.entry,
            comment="Nice post!",
            contentType="text/plain"
        )

    def test_get_comment_success(self):
        res = self.client.get(f"/api/Comment/{self.comment.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["id"], self.comment.id)

    def test_get_comment_not_found(self):
        fake_id = "https://node1.com/api/comments/missing"
        res = self.client.get(f"/api/Comment/{fake_id}/")
        self.assertEqual(res.status_code, 404)

class GETEntryImageAPITests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="imageauthor",
            email="image@example.com",
            is_approved=True
        )
        self.entry = Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.author,
            content="Post with images",
            visibility="PUBLIC"
        )
        self.entry_image = EntryImage.objects.create(
            entry=self.entry,
            image="test_image.jpg",
            order=0
        )

    def test_get_entry_image_success(self):
        res = self.client.get(f"/api/EntryImage/{self.entry_image.id}/")
        self.assertEqual(res.status_code, 200)

    def test_get_entry_image_not_found(self):
        res = self.client.get("/api/EntryImage/9999/")
        self.assertEqual(res.status_code, 404)
