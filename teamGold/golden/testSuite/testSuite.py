'''
Order of Terminal Commands to Run Tests:

Caveats Before Running (on new environments)
- pip install django
- pip install whitenoise 
- pip install pillow 
- rm db.sqlite3
- python manage.py makemigrations
- python manage.py migrate 
- python manage.py test
'''

# REST FRAMEWORK IMPORTS 
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

# DJANGO IMPORTS
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

# PYTHON IMPORTS
from base64 import b64encode
from urllib.parse import quote
import uuid, tempfile, io, shutil
from unittest.mock import patch, Mock
import logging

# LOCAL IMPORTS
from golden.models import Author, Entry, EntryImage, Node, Like, Comment, Follow

'''
This module contains comprehensive tests for all GET/POST/PUT/DELETE endpoints of the API, verifying 
that the system correctly retrieves resources by their fully qualified IDs (FQIDs).

Tested endpoints include:

- /api/Profile/<id>/ which retrieves author profiles.
- /api/Node/<id>/ which retrieves nodes/servers.
- /api/Follow/<id> which retrieves follow/follow-request activities.
- /api/Like/<id>/ which retrieves like activities.
- /api/Comment/<id>/ which retrieves comments on entries.

- /api/Entry/<id>/ which retrieves entries/posts.
- /api/Entry/<path:entry_id>/comments/ which retrieves an entry's comment thread 
- /api/EntryImage/<id>/ which retrieves images associated with entries.
- /api/Entry/<path:entry_id>/images/ which allows uploading images to an entry

Overview of HTTP Codes for the tests, ensuring the validity of:
1. Valid resource IDs to return a 200 OK with the correct data.
2. Invalid resource IDs return a 404 Not Found.
3. Request denied because lack of valid authentication credentials returning 401 Unauthorized

This suite supports automated testing for RESTful API compliance and interoperability 
with other nodes, as well as a basic model class.

TODO: ALL OF COMMENTING TEST SUITE
TODO: EDITING IMAGES FROM AN ENTRY 
TODO: OTHER NODE INTERACTIONS

'''

# ============================================================
# Helper Functions
# ============================================================

def make_fqid(base="https://node1.com", *parts):
    """Helper to generate a full qualified ID"""
    p = "/".join(str(p).strip("/") for p in parts if p is not None)
    return f"{base}/{p}"

def _basic_token(username, password):
    """Generate base64 encoded Basic Auth token"""
    return b64encode(f"{username}:{password}".encode()).decode()

class AuthenticatedAPITestCase(APITestCase):
    """Provides Basic Authenticated APIClient for tests"""
    def setUp(self):
        super().setUp()
        self.client = APIClient()

        AuthUser = get_user_model()
        self.apiuser, _ = AuthUser.objects.get_or_create(
            username="apiuser",
            defaults={"is_active": True}
        )
        if hasattr(self.apiuser, "is_approved"):
            self.apiuser.is_approved = True
        self.apiuser.set_password("pass")
        self.apiuser.save()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Basic {_basic_token('apiuser', 'pass')}"
        )

# ============================================================
# Model-Level Tests (Legacy, but useful)
# ============================================================

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

        self.comment = Comment.objects.create(
            id="https://node.example.com/api/authors/2/comments/200",
            author=self.author2,
            entry=self.entry,
            content="Nice post!"
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
            state="REQUESTED",
            published=timezone.now()
        )

    def test_author_unaccepted(self):
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
        self.assertEqual(self.comment.content, "Nice post!")

    def test_like_creation(self):
        self.assertEqual(self.like.object, self.entry.id)
        self.assertEqual(self.like.author, self.author2)

    def test_follow_creation(self):
        self.assertEqual(self.follow.actor, self.author2)
        self.assertEqual(self.follow.object, self.author1.id)
        self.assertEqual(self.follow.state, "REQUESTED")

    def test_entry_edit(self):
        self.entry.content = "Updated content"
        self.entry.save()
        updated_entry = Entry.objects.get(id=self.entry.id)
        self.assertEqual(updated_entry.content, "Updated content")

    def test_comment_reply(self):
        reply = Comment.objects.create(
            id="https://node.example.com/api/authors/1/comments/201",
            author=self.author1,
            entry=self.entry,
            reply_to=self.comment,
            content="Thanks!"
        )
        self.assertEqual(reply.reply_to, self.comment)
        self.assertIn(reply, self.comment.replies.all())

# ============================================================
# Profile/Author Related Test Suite
# ============================================================

class ProfileAPITests(AuthenticatedAPITestCase):
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

class AuthorizationAPITests(APITestCase):
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
        r1 = self.client.get(f"/api/Profile/{self.author.id}/")
        self.assertEqual(r1.status_code, 401)
        self.assertIn("WWW-Authenticate", r1)

        token = b64encode(b"apiuser:pass").decode()
        self.client.credentials(HTTP_AUTHORIZATION=f"Basic {token}")
        r2 = self.client.get(f"/api/Profile/{self.author.id}/")
        self.assertEqual(r2.status_code, 200)

class RelationshipsAPITests(AuthenticatedAPITestCase):
    """
    Comprehensive tests for follows, friends, likes, comments, visibility.
    """

    def setUp(self):
        super().setUp()

        self.a1 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="alice",
            email="a@example.com",
            is_approved=True
        )
        self.a2 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="bob",
            email="b@example.com",
            is_approved=True
        )
        self.a3 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="carol",
            email="c@example.com",
            is_approved=True
        )

        # user1 and user2 are mutuals
        Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=self.a1,
            object=self.a2.id,
            state="ACCEPTED",
            published=timezone.now()
        )
        Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=self.a2,
            object=self.a1.id,
            state="ACCEPTED",
            published=timezone.now()
        )
        # user3 follows user1, not mutuals
        Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=self.a3,
            object=self.a1.id,
            state="ACCEPTED",
            published=timezone.now()
        )

        self.entry = Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.a1,
            title="Alice's Post",
            content="This is Alice’s public post.",
            visibility="PUBLIC"
        )

        Like.objects.create(
            id=f"https://node1.com/api/likes/{uuid.uuid4()}",
            author=self.a2,
            object=self.entry.id,
            published=timezone.now()
        )

        self.comment = Comment.objects.create(
            id=f"https://node1.com/api/comments/{uuid.uuid4()}",
            author=self.a3,
            entry=self.entry,
            content="Great post!",
            published=timezone.now()
        )

    def test_follow_relationships_exist(self):
        """Verify one-way follow relationships"""
        self.assertTrue(Follow.objects.filter(actor=self.a1, object=self.a2.id).exists())
        self.assertTrue(Follow.objects.filter(actor=self.a2, object=self.a1.id).exists())
        self.assertTrue(Follow.objects.filter(actor=self.a3, object=self.a1.id).exists())

    def test_friendship_mutual_follow(self):
        """Ensure mutual follows register as friends"""
        res = self.client.get(f"/api/Author/{self.a1.id}/friends/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        friend_ids = [f["id"] for f in res.data]
        self.assertIn(self.a2.id, friend_ids)
        self.assertNotIn(self.a3.id, friend_ids)

    def test_entry_likes(self):
        """Confirm entry has expected likes"""
        res = self.client.get(f"/api/Entry/{self.entry.id}/") 
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        liked_by = Like.objects.filter(object=self.entry.id).values_list("author__id", flat=True)
        self.assertIn(self.a2.id, liked_by)

    def test_entry_comments(self):
        """Confirm entry has comments and content matches."""
        comments = Comment.objects.filter(entry=self.entry)
        self.assertEqual(comments.count(), 1)
        self.assertEqual(comments.first().content, "Great post!")

    def test_entry_visibility_public(self):
        """Public entries should be visible to any user"""
        res = self.client.get(f"/api/Entry/{self.entry.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["visibility"], "PUBLIC")

# ============================================================
# Entry Related Test Suites
# ============================================================

class EntryCRUDTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="entrymaker",
            email="entry@example.com",
            is_approved=True,
        )
        self.entry_id = f"https://node1.com/api/entries/{uuid.uuid4()}"
        self.entry = Entry.objects.create(
            id=self.entry_id,
            author=self.author,
            title="Initial Post",
            content="Body text",
            visibility="PUBLIC",
        )
        self.base_url = "/api/Entry/"

    def test_get_entry_success(self):
        res = self.client.get(f"{self.base_url}{self.entry.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], self.entry.id)

    def test_get_entry_not_found(self):
        fake_id = "https://node1.com/api/entries/invalid"
        res = self.client.get(f"{self.base_url}{fake_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_entry(self):
        new_id = f"https://node1.com/api/entries/{uuid.uuid4()}"
        data = {
            "id": new_id,
            "author": self.author.id,
            "title": "New Entry",
            "content": "This is a test post",
            "visibility": "UNLISTED"
        }
        res = self.client.post(f"/api/Entry/{new_id}/", data, format="json")
        self.assertIn(res.status_code, [200, 201])
        exists = Entry.objects.filter(id=new_id).exists()
        self.assertTrue(exists)

    def test_put_entry(self):
        update_data = {"title": "Updated Title", "content": "Updated Content"}
        res = self.client.put(
            f"/api/Entry/{self.entry.id}/", update_data, format="json"
        )
        self.assertIn(res.status_code, [200, 204])
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.title, "Updated Title")

    def test_delete_entry(self):
        res = self.client.delete(f"/api/Entry/{self.entry.id}/")
        self.assertIn(res.status_code, [200, 204, 202])
        still_exists = Entry.objects.filter(id=self.entry.id).exists()
        self.assertFalse(still_exists)

@override_settings(MEDIA_ROOT=tempfile.mkdtemp()) # Overriding MEDIA_ROOT for test isolation to not pollute the workspace 
class EntryImageAPITests(AuthenticatedAPITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls._overridden_settings['MEDIA_ROOT'], ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="imageuser",
            email="imageuser@example.com",
            is_approved=True,
        )
        self.entry = Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.author,
            title="Image Post",
            content="Post with image(s)",
            visibility="PUBLIC"
        )

        # Creates a mock uploaded image
        self.image_bytes = io.BytesIO(b"\x47\x49\x46\x38\x39\x61") 
        self.upload = SimpleUploadedFile(
            "tiny.gif", self.image_bytes.getvalue(), content_type="image/gif"
        )

        self.entry_image = EntryImage.objects.create(
            entry=self.entry,
            image="test_image.jpg",
            order=0
        )

        self.base_url = "/api/EntryImage/"

    def test_get_entry_image_success(self):
        res = self.client.get(f"{self.base_url}{self.entry_image.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], self.entry_image.id)

    def test_get_entry_image_not_found(self):
        res = self.client.get(f"{self.base_url}9999/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_entry_image(self):
        image = EntryImage.objects.create(entry=self.entry, image=self.upload, order=1)
        res = self.client.delete(f"{self.base_url}{image.id}/")
        self.assertIn(res.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT, status.HTTP_202_ACCEPTED])
        self.assertFalse(EntryImage.objects.filter(id=image.id).exists())

class LikeAPITests(AuthenticatedAPITestCase):
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

class CommentAPITests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        logging.basicConfig(level=logging.DEBUG)
        # create an entry to comment on (author may be different)
        base = getattr(settings, 'LOCAL_NODE_URL', None) or getattr(settings, 'SITE_URL', 'http://local')
        base = base.rstrip('/')
        self.entry_author = Author.objects.create(
            id=f"{base}/api/authors/{uuid.uuid4()}",
            username='entry_author'
        )
        self.entry = Entry.objects.create(
            id=f"{base}/api/entries/{uuid.uuid4()}",
            author=self.entry_author,
            content="test entry",
            title="Test"
        )

    def test_post_comment_success(self):
        enc = quote(self.entry.id.rstrip('/'), safe='')
        url = f"/api/entries/{enc}/comments/"
        payload = {"content":"Testing comment API", "contentType":"text/plain"}
        res = self.client.post(url, payload, format="json")
        self.assertIn(res.status_code, (200, 201, 202))
    
    def test_post_comment_failure(self):
        enc = quote(self.entry.id.rstrip('/'), safe='')
        url = f"/api/entries/{enc}/comments/"
        payload = {"content":""}
        res = self.client.post(url, payload, format="json")
        self.assertIn(res.status_code, (400,))
    
    def test_get_comments(self):
        # create a proper Author for the comment
        test_author = Author.objects.create(
            id=f"{settings.SITE_URL}/api/authors/{uuid.uuid4()}",
            username="commenter"
        )
        Comment.objects.create(
            id=f"{settings.SITE_URL.rstrip('/')}/api/comments/{uuid.uuid4()}",
            author=test_author,
            entry=self.entry,
            content="Existing comment",
            published=timezone.now()
        )
        enc = quote(self.entry.id.rstrip('/'), safe='')
        url = f"/api/entries/{enc}/comments/"
        print('TEST URL:', url, flush=True)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        
class RemoteCommentsTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        # enable debug logging for test visibility
        logging.basicConfig(level=logging.DEBUG)
        # mark the test node as active so get_remote_node_from_fqid() recognizes it
        Node.objects.create(id="http://nodebbbb/", auth_user="remoteuser", auth_pass="remotepass", is_active=True)

    @patch("golden.api.commentAPIView.requests.get")
    def test_remote_comments(self, mock_get):
        mock_res = Mock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "type": "comments",
            "id": "http://nodebbbb/api/entries/.../comments/",
            "size": 1,
            "items": [{
                "id": "http://nodebbbb/comment/1",
                "author": {"id": "http://nodebbbb/author/1/"},
                "content": "remote!",
                "contentType": "text/plain",
            }]
        }
        mock_get.return_value = mock_res

        remote_entry = "http://nodebbbb/api/authors/222/entries/249/"
        enc = quote(remote_entry, safe='').rstrip('/')
        res = self.client.get(f"/api/entries/{enc}/comments/")
        print('DEBUG: mock_get.called=', mock_get.called, 'call_args=', mock_get.call_args, 'res.status_code=', getattr(res, 'status_code', None), flush=True)
        self.assertEqual(res.status_code, 200)

        # assert code called the expected remote URL
        expected_url = "http://nodebbbb/api/entries/" + enc + "/comments/"
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        self.assertIn("nodebbbb", called_url)

    @patch("golden.api.commentAPIView.requests.post")
    def test_post_forwarding(self, mock_post):
        """Ensure that when a comment is posted to an entry whose author is on a remote node,
        the server forwards the saved comment to that node's inbox via POST.
        """
        # prepare mock response for post
        mock_res = Mock()
        mock_res.status_code = 201
        mock_post.return_value = mock_res

        # Create an author representing the remote entry owner (actor)
        remote_actor = Author.objects.create(
            id="http://nodebbbb/api/authors/222/",
            username="remote_owner",
        )

        # Create a local Entry that references the remote actor as its author
        entry = Entry.objects.create(
            id=f"http://local.example.com/api/entries/{uuid.uuid4()}/",
            author=remote_actor,
            title="Remote-owned post",
            content="content",
            visibility="PUBLIC",
        )

        # Create a local commenter author to include in the POST payload
        commenter = Author.objects.create(
            id=f"http://local.example.com/api/authors/{uuid.uuid4()}/",
            username="local_commenter",
        )

        enc = quote(entry.id.rstrip('/'), safe='')
        # use the Entry/ alias which passes `entry_id` to the view POST handler
        url = f"/api/Entry/{enc}/comments/"

        payload = {
            "content": "Forward this comment",
            "contentType": "text/plain",
            "author": {"id": commenter.id},
        }

        res = self.client.post(url, payload, format="json")

        # debug output for failing validation
        print('POST res.status_code=', res.status_code, 'res.data=', getattr(res, 'data', None), flush=True)

        # view should accept and create the comment
        self.assertIn(res.status_code, (200, 201, 202))

        # The inbox URL should be the remote node's base + '/inbox'
        expected_inbox_prefix = "http://nodebbbb"  # our Node created in setUp has this base
        self.assertTrue(mock_post.called, "requests.post should have been called to forward the comment")
        called_url = mock_post.call_args[0][0]
        self.assertIn(expected_inbox_prefix, called_url)

# ============================================================
# Note Related Test Suites
# ============================================================

class NodeAPITests(AuthenticatedAPITestCase):
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