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

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone

from base64 import b64encode
from unittest.mock import patch, Mock
import uuid

from golden.models import Author, Entry, Comment, Like
from golden.activities import (
    make_fqid,
    is_local,
    create_new_entry_activity,
    create_update_entry_activity,
    create_delete_entry_activity,
    create_comment_activity,
    create_like_activity,
    create_unlike_activity,
    create_follow_activity,
    create_profile_update_activity,
    get_comment_list_api,
    get_like_api
)

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

'''

# ============================================================
# Entry Related Activity Tests
# ============================================================

class CreateNewEntryActivityTestCase(TestCase):
    def setUp(self):
        self.author = Mock()
        self.author.id = "https://example.com/api/authors/author-uuid"
        self.author.username = "testuser"
        self.author.host = "https://example.com"
        self.author.web = "https://example.com/authors/author-uuid"
        self.author.github = "https://github.com/testuser"
        self.author.profileImage = None

        self.entry = Mock()
        self.entry.id = "https://example.com/api/entries/entry-uuid"
        self.entry.title = "Test Entry"
        self.entry.web = "https://example.com/entry/entry-uuid"
        self.entry.description = "Test description"
        self.entry.contentType = "text/plain"
        self.entry.content = "Test content"
        self.entry.published = timezone.now().isoformat()
        self.entry.visibility = "PUBLIC"

    @patch("golden.activities.get_comment_list_api")
    @patch("golden.activities.get_like_api")
    def test_create_new_entry_activity(self, mock_like, mock_comment):
        mock_comment.return_value = {}
        mock_like.return_value = {}

        activity = create_new_entry_activity(self.author, self.entry)

        self.assertEqual(activity["type"], "Entry")
        self.assertEqual(activity["title"], "Test Entry")
        self.assertEqual(activity["id"], self.entry.id)
        self.assertEqual(activity["visibility"], "PUBLIC")

        self.assertEqual(activity["author"]["displayName"], "testuser")
        self.assertEqual(activity["comments"], {})
        self.assertEqual(activity["likes"], {})

class CreateUpdateEntryActivityTestCase(TestCase):
    def setUp(self):
        self.author = Mock()
        self.author.id = "https://example.com/api/authors/author-uuid"
        self.author.username = "testuser"
        self.author.host = "https://example.com"
        self.author.web = "https://example.com/authors/author-uuid"
        self.author.github = "https://github.com/testuser"
        self.author.profileImage = None

        self.entry = Mock()
        self.entry.id = "https://example.com/api/entries/entry-uuid"
        self.entry.title = "Updated Entry"
        self.entry.web = "https://example.com/entry/entry-uuid"
        self.entry.description = "Updated description"
        self.entry.contentType = "text/markdown"
        self.entry.content = "# Updated content"
        self.entry.published = timezone.now().isoformat()
        self.entry.visibility = "FRIENDS"

    @patch("golden.activities.get_comment_list_api")
    @patch("golden.activities.get_like_api")
    def test_create_update_entry_activity(self, mock_like, mock_comment):
        comment_list = [{"comment": "test"}]
        like_list = [{"author": "someone"}]

        mock_comment.return_value = comment_list
        mock_like.return_value = like_list

        activity = create_update_entry_activity(self.author, self.entry)

        self.assertEqual(activity["type"], "Entry")
        self.assertEqual(activity["title"], "Updated Entry")
        self.assertEqual(activity["comments"], comment_list)
        self.assertEqual(activity["likes"], like_list)
        self.assertEqual(activity["visibility"], "FRIENDS")

class CreateDeleteEntryActivityTestCase(TestCase):
    def setUp(self):
        self.author = Mock()
        self.author.id = "https://example.com/api/authors/author-uuid"
        self.author.username = "testuser"
        self.author.host = "https://example.com"
        self.author.web = "https://example.com/authors/author-uuid"
        self.author.github = "https://github.com/testuser"
        self.author.profileImage = None

        self.entry = Mock()
        self.entry.id = "https://example.com/api/entries/entry-uuid"
        self.entry.title = "Deleted Entry"
        self.entry.web = "https://example.com/entry/entry-uuid"
        self.entry.description = "To be deleted"
        self.entry.contentType = "text/plain"
        self.entry.content = "Content"
        self.entry.published = timezone.now().isoformat()
        self.entry.visibility = "PUBLIC"

    @patch("golden.activities.get_comment_list_api")
    @patch("golden.activities.get_like_api")
    def test_create_delete_entry_activity(self, mock_like, mock_comment):
        mock_comment.return_value = []
        mock_like.return_value = []

        activity = create_delete_entry_activity(self.author, self.entry)

        self.assertEqual(activity["type"], "Entry")
        self.assertEqual(activity["visibility"], "DELETED")
        self.assertIn("/posts/", activity["id"])

class EntryActivityVisibilityTestCase(TestCase):
    def setUp(self):
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="visauthor",
            email="vis@example.com",
            host="https://node1.com/api/",
            is_approved=True,
        )

    def _create_entry(self, visibility):
        return Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.author,
            title="Visibility Test",
            content="Test Content",
            contentType="text/plain",
            description="desc",
            visibility=visibility,
        )

    def test_public_visibility(self):
        entry = self._create_entry("PUBLIC")
        activity = create_update_entry_activity(self.author, entry)
        self.assertEqual(activity["visibility"], "PUBLIC")

    def test_friends_visibility(self):
        entry = self._create_entry("FRIENDS")
        activity = create_update_entry_activity(self.author, entry)
        self.assertEqual(activity["visibility"], "FRIENDS")

# ============================================================
# Comment / Like / Unlike Activity Tests
# ============================================================

class CreateCommentActivityTestCase(TestCase):
    def setUp(self):
        self.author = Mock()
        self.author.id = "https://example.com/api/authors/author-uuid"
        self.author.name = "Test User"
        self.author.web = "https://example.com/authors/author-uuid"
        self.author.host = "https://example.com"
        self.author.github = "https://github.com/testuser"
        self.author.profileImage = None

        self.entry = Mock()
        self.entry.id = "https://example.com/api/entries/entry-uuid"

        self.comment = Mock()
        self.comment.content = "This is a comment"
        self.comment.contentType = "text/plain"
        self.comment.published = timezone.now().isoformat()

    def test_create_comment_activity(self):
        activity = create_comment_activity(self.author, self.entry, self.comment)

        self.assertEqual(activity["type"], "comment")
        self.assertEqual(activity["comment"], "This is a comment")
        self.assertEqual(activity["author"]["displayName"], "Test User")
        self.assertEqual(activity["entry"], self.entry.id)
        self.assertIn("/comments/", activity["id"])

class CreateLikeActivityTestCase(TestCase):
    def setUp(self):
        self.author = Mock()
        self.author.id = "https://example.com/api/authors/author-uuid"
        self.author.name = "Test User"
        self.author.web = "https://example.com/authors/author-uuid"
        self.author.host = "https://example.com"
        self.author.github = "https://github.com/testuser"
        self.author.profileImage = None

    def test_create_like_activity(self):
        liked_object = "https://example.com/api/entries/entry-uuid"

        activity = create_like_activity(self.author, liked_object)

        self.assertEqual(activity["type"], "like")
        self.assertEqual(activity["object"], liked_object)
        self.assertEqual(activity["author"]["displayName"], "Test User")
        self.assertIn("/likes/", activity["id"])
        self.assertIsNotNone(activity["published"])

class CreateUnlikeActivityTestCase(TestCase):    
    def setUp(self):
        self.author = Mock()
        self.author.id = "https://example.com/api/authors/author-uuid"
        self.author.username = "testuser"
        self.author.name = "testuser"      # <-- FIXED
        self.author.host = "https://example.com"
        self.author.web = "https://example.com/authors/author-uuid"
        self.author.github = "https://github.com/testuser"
        self.author.profileImage = None

        self.liked_object = Mock()
        self.liked_object.id = "https://example.com/api/likes/like-uuid"
        self.liked_object.published = timezone.now().isoformat()
        self.liked_object.object = "https://example.com/api/entries/entry-uuid"

        self.liked_object.author = Mock()
        self.liked_object.author.id = "https://example.com/api/authors/other-uuid"
        self.liked_object.author.username = "otheruser"
        self.liked_object.author.name = "otheruser"  
        self.liked_object.author.host = "https://example.com"
        self.liked_object.author.web = "https://example.com/authors/other-uuid"
        self.liked_object.author.github = "https://github.com/otheruser"
        self.liked_object.author.profileImage = None

    def test_create_unlike_activity(self):
        activity = create_unlike_activity(self.author, self.liked_object)
        obj = activity["object"]

        self.assertEqual(activity["type"], "unlike")
        self.assertIn("/unlike/", activity["id"])
        self.assertIn("author", activity)
        self.assertEqual(activity["author"]["displayName"], "testuser")
        self.assertIs(obj, self.liked_object)
        self.assertEqual(obj.id, self.liked_object.id)
        self.assertEqual(obj.object, self.liked_object.object)
        self.assertEqual(obj.author.id, self.liked_object.author.id)

# ============================================================
# Author Related Tests
# ============================================================

class CreateFollowActivityTestCase(TestCase):
    def setUp(self):
        self.author = Mock()
        self.author.id = "https://example.com/api/authors/follower-uuid"
        self.author.username = "follower"
        self.author.name = "Follower User"
        self.author.host = "https://example.com"
        self.author.web = "https://example.com/authors/follower-uuid"
        self.author.github = "https://github.com/follower"
        self.author.profileImage = None

        self.target = Mock()
        self.target.id = "https://example.com/api/authors/target-uuid"
        self.target.username = "target"
        self.target.name = "Target User"
        self.target.host = "https://example.com"
        self.target.web = "https://example.com/authors/target-uuid"
        self.target.github = "https://github.com/target"
        self.target.profileImage = None

    def test_create_follow_activity(self):
        activity = create_follow_activity(self.author, self.target)

        self.assertEqual(activity["type"], "follow")
        self.assertEqual(activity["summary"], "Follower User wants to follow Target User")
        self.assertEqual(activity["actor"]["id"], self.author.id)
        self.assertEqual(activity["object"]["id"], self.target.id)
        self.assertEqual(activity["state"], "REQUESTED")
        self.assertIsNotNone(activity["published"])

class ProfileUpdateActivityTests(TestCase):
    def setUp(self):
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="tester",
            email="test@example.com",
            host="https://node1.com/api/",
            github="https://github.com/tester",
            is_approved=True,
        )

    def test_profile_update_activity_structure(self):
        activity = create_profile_update_activity(self.author)

        self.assertEqual(activity["type"], "Update")
        self.assertIn("id", activity)
        self.assertEqual(activity["actor"]["id"], str(self.author.id))
        self.assertEqual(activity["object"]["id"], str(self.author.id))

        self.assertEqual(
            activity["summary"],
            f"{self.author.username} updated their profile"
        )

        self.assertIn("published", activity)




'''
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
        self.client.force_authenticate(user=self.apiuser)

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

class EntryVisibilityTests(APITestCase):
    def setUp(self):
        User = get_user_model()

        # Owner of the post
        self.owner_user = User.objects.create_user(username="owner", password="pw")
        self.owner_author = Author.from_user(self.owner_user)

        # Follower (follows owner)
        self.follower_user = User.objects.create_user(username="follower", password="pw")
        self.follower_author = Author.from_user(self.follower_user)
        Follow.objects.create(
            id=f"{self.follower_author.id.rstrip('/')}/follow-test-owner",
            actor=self.follower_author,
            object=self.owner_author.id,
            state="ACCEPTED",
        )

        # Friend (mutual follow with owner)
        self.friend_user = User.objects.create_user(username="friend", password="pw")
        self.friend_author = Author.from_user(self.friend_user)
        # friend → owner
        Follow.objects.create(
            id=f"{self.friend_author.id.rstrip('/')}/follow-test-owner-friend",
            actor=self.friend_author,
            object=self.owner_author.id,
            state="ACCEPTED",
        )
        # owner → friend
        Follow.objects.create(
            id=f"{self.owner_author.id.rstrip('/')}/follow-test-friend-owner",
            actor=self.owner_author,
            object=self.friend_author.id,
            state="ACCEPTED",
        )

        # Stranger (no follow relationship)
        self.stranger_user = User.objects.create_user(username="stranger", password="pw")
        self.stranger_author = Author.from_user(self.stranger_user)

        # Entries with different visibility
        self.public_entry = Entry.objects.create(
            id=f"{self.owner_author.id.rstrip('/')}/posts/public-test",
            author=self.owner_author,
            content="public content",
            visibility="PUBLIC",
        )
        self.unlisted_entry = Entry.objects.create(
            id=f"{self.owner_author.id.rstrip('/')}/posts/unlisted-test",
            author=self.owner_author,
            content="unlisted content",
            visibility="UNLISTED",
        )
        self.friends_entry = Entry.objects.create(
            id=f"{self.owner_author.id.rstrip('/')}/posts/friends-test",
            author=self.owner_author,
            content="friends content",
            visibility="FRIENDS",
        )

    def test_entry_visibility_public(self):
        """Public entries should be visible to any authenticated user"""
        self.client.force_authenticate(user=self.stranger_user)
        res = self.client.get(f"/api/Entry/{self.public_entry.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["visibility"], "PUBLIC")

    def test_entry_visibility_unlisted_visible_to_follower(self):
        """Unlisted entry should be visible to a follower"""
        self.client.force_authenticate(user=self.follower_user)
        res = self.client.get(f"/api/Entry/{self.unlisted_entry.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["visibility"], "UNLISTED")

    def test_entry_visibility_unlisted_hidden_from_stranger(self):
        """Unlisted entry should not be visible to a non follower"""
        self.client.force_authenticate(user=self.stranger_user)
        res = self.client.get(f"/api/Entry/{self.unlisted_entry.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_entry_visibility_friends_visible_to_friend(self):
        """Friends-only entry should be visible to a mutual follower (friend)"""
        self.client.force_authenticate(user=self.friend_user)
        res = self.client.get(f"/api/Entry/{self.friends_entry.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["visibility"], "FRIENDS")

    def test_entry_visibility_friends_hidden_from_follower_only(self):
        """Friends-only entry should not be visible to a one-way follower"""
        self.client.force_authenticate(user=self.follower_user)
        res = self.client.get(f"/api/Entry/{self.friends_entry.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_entry_visibility_friends_hidden_from_stranger(self):
        """Friends-only entry should not be visible to unrelated users"""
        self.client.force_authenticate(user=self.stranger_user)
        res = self.client.get(f"/api/Entry/{self.friends_entry.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class AuthorFriendsAPITests(AuthenticatedAPITestCase):
    """
    Test coverage for AuthorFriendsView
    Tests retrieval of mutual followers (friends)
    """
    
    def setUp(self):
        super().setUp()
        self.author1 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="alice",
            email="alice@example.com",
            is_approved=True
        )
        self.author2 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="bob",
            email="bob@example.com",
            is_approved=True
        )
        self.author3 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="charlie",
            email="charlie@example.com",
            is_approved=True
        )
        
        # Make author1 and author2 mutual followers (friends)
        Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=self.author1,
            object=self.author2.id,
            state="ACCEPTED",
            published=timezone.now()
        )
        Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=self.author2,
            object=self.author1.id,
            state="ACCEPTED",
            published=timezone.now()
        )
        
        # Author3 follows author1 (not mutual)
        Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=self.author3,
            object=self.author1.id,
            state="ACCEPTED",
            published=timezone.now()
        )

    def test_get_friends_success(self):
        """GET should return only mutual followers"""
        res = self.client.get(f"/api/Author/{self.author1.id}/friends/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        friend_ids = [f["id"] for f in res.data]
        self.assertIn(self.author2.id, friend_ids)
        self.assertNotIn(self.author3.id, friend_ids)
        
    def test_get_friends_no_friends(self):
        """GET should return empty list if no mutual followers"""
        lonely_author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="lonely",
            email="lonely@example.com",
            is_approved=True
        )
        res = self.client.get(f"/api/Author/{lonely_author.id}/friends/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 0)
        
    def test_get_friends_author_not_found(self):
        """GET should return 404 if author doesn't exist"""
        fake_id = f"https://node1.com/api/authors/{uuid.uuid4()}"
        res = self.client.get(f"/api/Author/{fake_id}/friends/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        
    def test_get_friends_only_accepted_follows(self):
        """GET should only count ACCEPTED follows as friendships"""
        author4 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="dave",
            email="dave@example.com",
            is_approved=True
        )
        
        # Create pending follow requests (not accepted)
        Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=self.author1,
            object=author4.id,
            state="REQUESTED",
            published=timezone.now()
        )
        Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=author4,
            object=self.author1.id,
            state="REQUESTED",
            published=timezone.now()
        )
        
        res = self.client.get(f"/api/Author/{self.author1.id}/friends/")
        friend_ids = [f["id"] for f in res.data]
        self.assertNotIn(author4.id, friend_ids)


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

class EntryCommentAPITests(AuthenticatedAPITestCase):
    """
    Complete test coverage for EntryCommentAPIView
    Tests GET, POST, and DELETE operations on entry comments
    """
    
    def setUp(self):
        super().setUp()
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="commenter",
            email="comment@example.com",
            github="example@github",
            is_approved=True
        )
        self.entry = Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.author,
            title="Post with Comments",
            content="Comment on this!",
            visibility="PUBLIC"
        )
        self.comment1 = Comment.objects.create(
            id=f"https://node1.com/api/comments/{uuid.uuid4()}",
            author=self.author,
            entry=self.entry,
            content="First comment",
            published=timezone.now()
        )
        self.comment2 = Comment.objects.create(
            id=f"https://node1.com/api/comments/{uuid.uuid4()}",
            author=self.author,
            entry=self.entry,
            content="Second comment",
            published=timezone.now()
        )

    def test_get_entry_comments_success(self):
        """GET should return all comments for an entry"""
        res = self.client.get(f"/api/Entry/{self.entry.id}/comments/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 2)
        
    def test_get_entry_comments_ordered(self):
        """Comments should be ordered by published date (newest first)"""
        res = self.client.get(f"/api/Entry/{self.entry.id}/comments/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Most recent should be first (comment2 was created after comment1)
        self.assertEqual(res.data[0]["content"], "Second comment")

    def test_post_comment_success(self):
        """POST should create a new comment on an entry"""
        data = {
            "content": "New test comment",
            "published": timezone.now().isoformat()
        }
        res = self.client.post(
            f"/api/Entry/{self.entry.id}/comments/", 
            data, 
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Comment.objects.filter(entry=self.entry).count(), 3)
        
    def test_post_comment_entry_not_found(self):
        """POST should return 404 if entry doesn't exist"""
        fake_id = f"https://node1.com/api/entries/{uuid.uuid4()}"
        data = {"content": "Comment on nothing"}
        res = self.client.post(
            f"/api/Entry/{fake_id}/comments/", 
            data, 
            format="json"
        )
        print("RESPONSE STATUS:", res.status_code, flush=True)
        print("RESPONSE BODY:", getattr(res, "data", None) or res.content, flush=True)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        
    def test_post_comment_invalid_data(self):
        """POST should return 400 with invalid data"""
        data = {}  # Missing required content field
        res = self.client.post(
            f"/api/Entry/{self.entry.id}/comments/", 
            data, 
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # def test_delete_specific_comment(self):
    #     """DELETE with comment id should delete only that comment"""
    #     res = self.client.delete(
    #         f"/api/Entry/{self.entry.id}/comments/?id={self.comment1.id}"
    #     )
    #     self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
    #     self.assertFalse(Comment.objects.filter(id=self.comment1.id).exists())
    #     self.assertTrue(Comment.objects.filter(id=self.comment2.id).exists())
        
    # def test_delete_all_comments(self):
    #     """DELETE without comment id should delete all entry comments"""
    #     res = self.client.delete(f"/api/Entry/{self.entry.id}/comments/")
    #     self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
    #     self.assertEqual(Comment.objects.filter(entry=self.entry).count(), 0)
        
    # def test_delete_comment_not_found(self):
    #     """DELETE should return 404 if specific comment doesn't exist"""
    #     fake_id = f"https://node1.com/api/comments/{uuid.uuid4()}"
    #     res = self.client.delete(
    #         f"/api/Entry/{self.entry.id}/comments/?id={fake_id}"
    #     )
    #     self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        
    # def test_delete_entry_not_found(self):
    #     """DELETE should return 404 if entry doesn't exist"""
    #     fake_id = f"https://node1.com/api/entries/{uuid.uuid4()}"
    #     res = self.client.delete(f"/api/Entry/{fake_id}/comments/")
    #     self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

# ============================================================
# MISSING TEST CASES - Comment Likes
# ============================================================

class CommentLikeAPITests(AuthenticatedAPITestCase):
    """
    Complete test coverage for CommentLikeAPIView
    Tests GET and POST operations on comment likes
    """
    
    def setUp(self):
        super().setUp()
        self.author1 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="author1",
            email="a1@example.com",
            is_approved=True
        )
        self.author2 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="author2",
            email="a2@example.com",
            is_approved=True
        )
        self.entry = Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.author1,
            title="Entry with comment",
            content="Content",
            visibility="PUBLIC"
        )
        self.comment = Comment.objects.create(
            id=f"https://node1.com/api/comments/{uuid.uuid4()}",
            author=self.author1,
            entry=self.entry,
            content="A comment to like",
            published=timezone.now()
        )
        # Create some likes
        for i in range(3):
            Like.objects.create(
                id=f"https://node1.com/api/likes/{uuid.uuid4()}",
                author=self.author1,
                object=self.comment.id,
                published=timezone.now()
            )

    def test_get_comment_likes_success(self):
        """GET should return paginated likes for a comment"""
        res = self.client.get(f"/api/Comment/{self.comment.id}/likes/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["type"], "likes")
        self.assertEqual(res.data["count"], 3)
        
    def test_get_comment_likes_pagination(self):
        """GET should respect pagination parameters"""
        res = self.client.get(
            f"/api/Comment/{self.comment.id}/likes/?page=1&size=2"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["page_number"], 1)
        self.assertEqual(res.data["size"], 2)
        self.assertEqual(len(res.data["src"]), 2)
        
    def test_get_comment_likes_invalid_pagination(self):
        """GET should handle invalid pagination gracefully"""
        res = self.client.get(
            f"/api/Comment/{self.comment.id}/likes/?page=invalid&size=bad"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Should default to page=1, size=5
        self.assertEqual(res.data["page_number"], 1)
        self.assertEqual(res.data["size"], 5)

    def test_post_comment_like_success(self):
        """POST should create a new like on a comment"""
        # Use author2 to like the comment
        User = get_user_model()
        user2, _ = User.objects.get_or_create(
            username="user2",
            defaults={"is_active": True}
        )
        user2.set_password("pass2")
        if hasattr(user2, "is_approved"):
            user2.is_approved = True
        user2.save()
        
        client2 = APIClient()
        client2.credentials(
            HTTP_AUTHORIZATION=f"Basic {_basic_token('user2', 'pass2')}"
        )
        
        initial_count = Like.objects.filter(object=self.comment.id).count()
        res = client2.post(f"/api/Comment/{self.comment.id}/likes/")
        
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Like.objects.filter(object=self.comment.id).count(), 
            initial_count + 1
        )
        
    def test_post_comment_like_idempotent(self):
        """POST should be idempotent - return existing like if already liked"""
        # First like
        res1 = self.client.post(f"/api/Comment/{self.comment.id}/likes/")
        like_id_1 = res1.data["id"]
        
        # Try to like again
        res2 = self.client.post(f"/api/Comment/{self.comment.id}/likes/")
        like_id_2 = res2.data["id"]
        
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(like_id_1, like_id_2)
        
    def test_post_comment_like_comment_not_found(self):
        """POST should return 404 if comment doesn't exist"""
        fake_id = f"https://node1.com/api/comments/{uuid.uuid4()}"
        res = self.client.post(f"/api/Comment/{fake_id}/likes/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_comment_like_by_id(self):
        """GET /api/Like/<like_id>/ should return a Like that targets a comment."""
        # Create a like that targets the existing comment
        like = Like.objects.create(
            id=f"https://node1.com/api/likes/{uuid.uuid4()}",
            author=self.author1,
            object=self.comment.id,
            published=timezone.now()
        )
        res = self.client.get(f"/api/Like/{like.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data.get("id"), like.id)

# ============================================================
# Remote node / federation related tests
# ============================================================

class RemoteTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        # create an active remote node record used by the view to detect remote hosts
        Node.objects.create(id="http://nodebbbb/", auth_user="remoteuser", auth_pass="remotepass", is_active=True)


    @patch("golden.api.commentAPIView.requests.get")
    def test_get_remote_comments(self, mock_get):
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
        enc = quote(remote_entry.rstrip('/'), safe='')
        res = self.client.get(f"/api/entries/{enc}/comments/")
        self.assertEqual(res.status_code, 200)

        # assert our code called the expected remote URL
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        self.assertIn("nodebbbb", called_url)

    @patch("golden.api.commentAPIView.requests.post")
    def test_remote_comment_post(self, mock_post):
        """Ensure that when a comment is posted to an entry whose author is on a remote node,
        the server forwards the saved comment to that node's inbox via POST.
        """
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
        print(entry.id)
        enc = quote(entry.id.rstrip('/'), safe='')
        # use the Entry/ alias which passes `entry_id` to the view POST handler
        url = f"/api/Entry/{enc}/comments/"

        payload = {
            "content": "Forward this comment",
            "contentType": "text/plain",
            "author": {"id": commenter.id},
        }
        print(url)
        print(payload)
        res = self.client.post(url, payload, format="json")
        print(res)
        # view should accept and create the comment
        self.assertIn(res.status_code, (200, 201, 202))

        # The inbox URL should be the remote node's base + '/inbox'
        self.assertTrue(mock_post.called, "requests.post should have been called to forward the comment")
        called_url = mock_post.call_args[0][0]
        self.assertIn("nodebbbb", called_url)

    @patch("golden.api.likeAPIView.requests.post")
    def test_remote_like_post(self, mock_post):
        """Ensure that when a like is posted to an entry whose author is on a remote node,
        the server forwards the like to that node's inbox via POST.
        """
        mock_res = Mock()
        mock_res.status_code = 201
        mock_post.return_value = mock_res

        # Create a remote owner and entry owned by that remote actor
        remote_owner = Author.objects.create(
            id="http://nodebbbb/api/authors/333/",
            username="remote_like_owner",
        )

        entry = Entry.objects.create(
            id=f"http://local.example.com/api/entries/{uuid.uuid4()}/",
            author=remote_owner,
            title="Remote-owned like test",
            content="content",
            visibility="PUBLIC",
        )

        # Create a local liker author to include in the POST payload
        liker = Author.objects.create(
            id=f"http://local.example.com/api/authors/{uuid.uuid4()}/",
            username="local_liker",
        )

        enc = quote(entry.id.rstrip('/'), safe='')
        url = f"/api/Entry/{enc}/likes/"

        payload = {
            "author": {"id": liker.id},
            "object": entry.id,
        }

        res = self.client.post(url, payload, format="json")
        # view should accept and either create or forward the like
        self.assertIn(res.status_code, (200, 201, 202))

        # The inbox URL should be the remote node's base + '/inbox'
        self.assertTrue(mock_post.called, "requests.post should have been called to forward the like")
        called_url = mock_post.call_args[0][0]
        self.assertIn("nodebbbb", called_url)

    @patch("golden.api.likeAPIView.requests.get")
    def test_remote_like_get(self, mock_get):
        """Ensure GET /api/Like/<remote_like_id>/ proxies a remote like when not local."""
        mock_res = Mock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "type": "like",
            "id": "http://nodebbbb/api/likes/12345",
            "author": {"id": "http://nodebbbb/api/authors/999/"},
            "object": "http://local.example.com/api/entries/abc",
        }
        mock_get.return_value = mock_res

        remote_like_id = f"http://nodebbbb/api/likes/{uuid.uuid4()}"
        res = self.client.get(f"/api/Like/{remote_like_id}/")
        self.assertEqual(res.status_code, 200)
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        self.assertIn("nodebbbb", called_url)

    @patch("golden.api.likeAPIView.requests.get")
    def test_get_remote_comment_likes(self, mock_get):
        """Ensure that when requesting comment likes for a remote comment, we proxy the remote node."""
        mock_res = Mock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "type": "likes",
            "id": "http://nodebbbb/api/comments/.../likes/",
            "page_number": 1,
            "size": 5,
            "count": 2,
            "src": [
                {"id": "http://nodebbbb/api/likes/1", "author": {"id": "http://nodebbbb/api/authors/1/"}, "object": "http://nodebbbb/api/comments/1"},
                {"id": "http://nodebbbb/api/likes/2", "author": {"id": "http://nodebbbb/api/authors/2/"}, "object": "http://nodebbbb/api/comments/1"}
            ]
        }
        mock_get.return_value = mock_res

        remote_comment = "http://nodebbbb/api/comments/123/"
        enc = quote(remote_comment.rstrip('/'), safe='')
        res = self.client.get(f"/api/Comment/{enc}/likes/")
        self.assertEqual(res.status_code, 200)
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        self.assertIn("nodebbbb", called_url)

    @patch("golden.api.likeAPIView.requests.post")
    def test_remote_comment_like_post(self, mock_post):
        """Ensure that when a like is posted to a comment whose author is on a remote node,
        the server forwards the like to that node's inbox via POST.
        """
        mock_res = Mock()
        mock_res.status_code = 201
        mock_post.return_value = mock_res

        # Create a remote author and entry/comment owned by that remote actor
        remote_owner = Author.objects.create(
            id="http://nodebbbb/api/authors/444/",
            username="remote_comment_owner",
        )

        entry = Entry.objects.create(
            id=f"http://local.example.com/api/entries/{uuid.uuid4()}/",
            author=remote_owner,
            title="Remote-owned comment entry",
            content="content",
            visibility="PUBLIC",
        )

        comment = Comment.objects.create(
            id=f"http://local.example.com/api/comments/{uuid.uuid4()}/",
            author=remote_owner,
            entry=entry,
            content="A remote comment",
            published=timezone.now(),
        )

        # Create a local liker author
        liker = Author.objects.create(
            id=f"http://local.example.com/api/authors/{uuid.uuid4()}/",
            username="local_comment_liker",
        )

        enc = quote(comment.id.rstrip('/'), safe='')
        url = f"/api/Comment/{enc}/likes/"

        payload = {
            "author": {"id": liker.id},
            "object": comment.id,
        }

        res = self.client.post(url, payload, format="json")
        # view should accept and either create or forward the like
        self.assertIn(res.status_code, (200, 201, 202))

        # The inbox URL should be the remote node's base + '/inbox'
        self.assertTrue(mock_post.called, "requests.post should have been called to forward the comment-like")
        called_url = mock_post.call_args[0][0]
        self.assertIn("nodebbbb", called_url)
    
    

    @patch("golden.api.likeAPIView.requests.get")
    def test_remote_comment_like_get(self, mock_get):
        """Ensure GET of a remote like (by FQID) proxies the remote node for comment-likes too."""
        mock_res = Mock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "type": "like",
            "id": "http://nodebbbb/api/likes/99999",
            "author": {"id": "http://nodebbbb/api/authors/888/"},
            "object": "http://local.example.com/api/comments/abc",
        }
        mock_get.return_value = mock_res

        remote_like_id = f"http://nodebbbb/api/likes/{uuid.uuid4()}"
        res = self.client.get(f"/api/Like/{remote_like_id}/")
        self.assertEqual(res.status_code, 200)
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        self.assertIn("nodebbbb", called_url)
        
# ============================================================
# Node Related Test Suites
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

class ForbiddenAuthorizationTests(APITestCase):
    """
    Test 403 Forbidden responses for various authorization scenarios
    """
    
    def setUp(self):
        self.client = APIClient()
        
        # Create an unapproved user
        User = get_user_model()
        self.unapproved_user, _ = User.objects.get_or_create(
            username="unapproved",
            defaults={"is_active": True}
        )
        self.unapproved_user.set_password("pass")
        if hasattr(self.unapproved_user, "is_approved"):
            self.unapproved_user.is_approved = False  # Not approved
        self.unapproved_user.save()
        
        # Create test data
        self.author = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="testauthor",
            email="test@example.com",
            is_approved=True
        )
        self.entry = Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.author,
            title="Test Entry",
            content="Content",
            visibility="PUBLIC"
        )

    def test_403_unapproved_user_profile(self):
        """Unapproved user should get 403 when accessing profiles"""
        token = _basic_token("unapproved", "pass")
        self.client.credentials(HTTP_AUTHORIZATION=f"Basic {token}")
        
        res = self.client.get(f"/api/Profile/{self.author.id}/")
        # Depending on implementation, might be 401 or 403
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
        
    def test_403_invalid_credentials(self):
        """Invalid credentials should result in 401/403"""
        token = _basic_token("unapproved", "wrongpass")
        self.client.credentials(HTTP_AUTHORIZATION=f"Basic {token}")
        
        res = self.client.get(f"/api/Profile/{self.author.id}/")
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

# ============================================================
# MISSING TEST CASES - Follow API
# ============================================================

class FollowAPITests(AuthenticatedAPITestCase):
    """
    Test coverage for FollowAPIView
    """
    def setUp(self):
        super().setUp()
        self.author1 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="follower",
            email="follower@example.com",
            is_approved=True
        )
        self.author2 = Author.objects.create(
            id=f"https://node1.com/api/authors/{uuid.uuid4()}",
            username="followee",
            email="followee@example.com",
            is_approved=True
        )
        self.follow = Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=self.author1,
            object=self.author2.id,
            state="ACCEPTED",
            published=timezone.now()
        )

    def test_get_follow_success(self):
        """GET should return follow data"""
        res = self.client.get(f"/api/Follow/{self.follow.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], self.follow.id)
        
    def test_get_follow_not_found(self):
        """GET should return 404 if follow doesn't exist"""
        fake_id = f"https://node1.com/api/follows/{uuid.uuid4()}"
        res = self.client.get(f"/api/Follow/{fake_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_follow_contains_fields(self):
        """GET should return follow object with expected fields"""
        res = self.client.get(f"/api/Follow/{self.follow.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        # Check expected keys exist in serialized follow
        for key in ("id", "actor", "object", "state", "published"):
            self.assertIn(key, data)

    def test_follow_model_default_state(self):
        """Directly creating a Follow without state should default to REQUESTED"""
        new_follow = Follow.objects.create(
            id=f"https://node1.com/api/follows/{uuid.uuid4()}",
            actor=self.author1,
            object=self.author2.id,
            published=timezone.now()
        )
        self.assertIn(new_follow.state, ("REQUESTING", "REQUESTED"))

# ============================================================
# MISSING TEST CASES - Entry Images POST
# ============================================================

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class EntryImagePostTests(AuthenticatedAPITestCase):
    """
    Test POST operations for EntryImage creation
    """
    
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
            is_approved=True
        )
        self.entry = Entry.objects.create(
            id=f"https://node1.com/api/entries/{uuid.uuid4()}",
            author=self.author,
            title="Image Post",
            content="Post for images",
            visibility="PUBLIC"
        )

    def test_post_entry_image_success(self):
        """POST should create a new entry image"""
        image_bytes = io.BytesIO(b"\x47\x49\x46\x38\x39\x61")
        upload = SimpleUploadedFile(
            "test.gif", image_bytes.getvalue(), content_type="image/gif"
        )
        
        data = {"image": upload, "order": 0}
        res = self.client.post(
            f"/api/Entry/{self.entry.id}/images/",
            data,
            format="multipart"
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EntryImage.objects.filter(entry=self.entry).exists())
        
    def test_post_entry_image_no_entry_id(self):
        """POST should return 400 if entry_id not provided"""
        res = self.client.post("/api/Entry//images/", {})
        self.assertIn(res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND])
        
    def test_post_entry_image_entry_not_found(self):
        """POST should return 404 if entry doesn't exist"""
        fake_id = f"https://node1.com/api/entries/{uuid.uuid4()}"
        res = self.client.post(f"/api/Entry/{fake_id}/images/", {})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        '''