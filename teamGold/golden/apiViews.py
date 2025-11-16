# REST FRAMEWORK IMPORTS 
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# DJANGO IMPORTS
from django.shortcuts import get_object_or_404

# PYTHON IMPORTS
from urllib.parse import unquote, urlparse
import uuid
import requests
import json
from django.conf import settings
from django.utils import timezone
from django.core.paginator import Paginator

# LOCAL IMPORTS
from golden.models import Author, Entry, Comment, Like, Follow, Node, EntryImage
from golden.services import generate_comment_fqid, resolve_or_create_author

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# SERIALIZERS IMPORTS
from .serializers import (
    AuthorSerializer, EntrySerializer, NodeSerializer,
    FollowSerializer, LikeSerializer, CommentSerializer, EntryImageSerializer
)

'''
Django REST Framework view that returns authors profiles data
as JSON data for other API nodes 
    - when a remote node wants to display an authors profile from our local node
    - remote node sends a GET request to our API endpoint (http:://golden.node.com/api/profile/<id>)
    - our node handles the request and serializers authors data to JSON
    - Entry related class based API views also have POST, PUT, DELETE API  
    - REST endpoints 

inbox info (comment/like/follow):
    If the entry’s author is local to your node:
    - send the Object (comment/like/follow) to the inboxes of all followers of that author.
    - remote authors will also be able to see it
If the entry’s author is remote:
    - push the Object to the parent node’s inbox (POST /api/authors/{AUTHOR_FQID}/inbox).
    - That remote node will then handle
'''

class ProfileAPIView(APIView):
    """
    This API view handles GET requests to retrieve author profile data by ID.
    - GET /api/profile/<id>/ will then retrieve author profile data
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Author.objects.get(pk=id) 
        except Author.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(AuthorSerializer(obj).data, status=status.HTTP_200_OK)


class EntryAPIView(APIView):
    """
    This API view handles GET, POST, PUT, and DELETE requests for entries.
    - GET /api/Entry/<id>/ will then retrieve entry data
    - POST /api/Entry/<id>/ will then create a new entry
    - PUT /api/Entry/<id>/ will then update an existing entry
    - DELETE /api/Entry/<id>/ will then delete an entry
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Entry.objects.get(pk=id) 
        except Entry.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(EntrySerializer(obj).data, status=status.HTTP_200_OK)
    
    def post(self, request, id):
        """Create a new entry."""
        serializer = EntrySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, id):
        """Update an existing entry (partial or full)."""
        try:
            entry = Entry.objects.get(pk=id)
        except Entry.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = EntrySerializer(entry, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id):
        """Delete an entry."""
        try:
            entry = Entry.objects.get(pk=id)
            entry.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Entry.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)


class EntryImageAPIView(APIView):
    """
    This API view handles GET, POST, PUT, and DELETE requests for an entry's images.
    - GET /api/EntryImage/<id>/ is for retrieving an entry image
    - POST /api/Entry/<entry_id>/images/ is for creating a new entry
    - DELETE /api/EntryImage/<id>/ is for deleting an entry image
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id=None):
        try:
            obj = EntryImage.objects.get(pk=id)
        except EntryImage.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(EntryImageSerializer(obj).data, status=status.HTTP_200_OK)

    def post(self, request, entry_id=None):
        if not entry_id:
            return Response({'error': 'entry_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            entry = Entry.objects.get(pk=entry_id)
        except Entry.DoesNotExist:
            return Response({'error': 'Entry not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = EntryImageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(entry=entry)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id=None):
        try:
            obj = EntryImage.objects.get(pk=id)
        except EntryImage.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EntryCommentAPIView(APIView):
    """
    This API view handles GET, POST, PUT, and DELETE requests for an entry's comments
    GET /api/Entry/<entry_id>/comments/ is for all comments on an entry
    POST /api/Entry/<entry_id>/comments/ is for creating a new comment
    DELETE /api/Entry/<entry_id>/comments/ is for delete one or all comments 
    TODO: DELETE API IS NOT TESTED YET - we might not need it tbh
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]


    
    @swagger_auto_schema(
        operation_description='Gets all comments for an entry.',
        responses={
            200: openapi.Response(description="OK"),
            404: openapi.Response(description="Not found"),
            400: openapi.Response(description="Bad request"),
        }
    )
    def get(self, request, entry_id):
        comments = Comment.objects.filter(entry_id=entry_id).order_by('-published')
        serializer = CommentSerializer(comments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


    @swagger_auto_schema(
        operation_summary='Adding a comment to an entry',
        operation_description='Client sends a POST request to comment on an entry',
        request_body=CommentSerializer,
        responses={
            201: openapi.Response(description="Comment Created"),
            404: openapi.Response(description="Not found"),
            400: openapi.Response(description="Comment creation failure"),
        }
    )
    def post(self, request, entry_id):
        # normalize data
        # validate request body
        # save comment to database with unique FQID
        # forward to inbox (if remote)
        # return response in JSON
        entry_id = unquote(entry_id).rstrip("/") # decode fqid to url
        entry = get_object_or_404(Entry, id=entry_id)
       
        if request.content_type != 'application/json':
            return Response({'detail': 'Content-Type must be application/json'}, status=status.HTTP_400_BAD_REQUEST)
        
        # server side fields
        data = request.data.copy()
        # author will be a nested object
        # we need to look it up on our local database or resolve it to a remote author
        incoming = request.data.get('author')   # could be str, dict, or missing
    
        try:
            author = resolve_or_create_author(incoming, create_if_missing = True)
        except Author.DoesNotExist:
            return Response({'detail':'Author not found'}, status=400)

        data["entry"] = entry.id #id == fqid
        data["author"] = author
        data["type"] = "comment"
        data["entry"] = entry.id #id == fqid
        # generate FQID (service expects (author, entry))
        # e.g. "id":"http://nodeaaaa/api/authors/<author_uuid>/commented/<uuid>"
        comment_id = generate_comment_fqid(author, entry)
        data["id"] = comment_id
        data["published"] = timezone.now().isoformat()

        # create comment instance in database
        # serializer maps data->json fields
        try:
            print("DEBUG: Comment payload (data) =", json.dumps(data, indent=2, default=str))
        except Exception:
            # fallback if data contains non-JSONable objects
            print("DEBUG: Comment payload (repr) =", repr(data))

        serializer = CommentSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        comment = serializer.save(author=author)

        # if the entry author is remote, attempt to POST the comment
        # to that node's inbox. Determine the parent node by matching the author's host.
        try:
            # Serialize the saved comment for sending
            comment_object = CommentSerializer(comment).data

            # parse host from the entry's author's id (FQID)
            actor_id = getattr(entry.author, 'id', None)
            if actor_id:
                parsed = urlparse(actor_id)
                actor_host = f"{parsed.scheme}://{parsed.netloc}"
                parent_node = Node.objects.filter(id__startswith=actor_host).first()
            else:
                parent_node = None

            if parent_node and parent_node.id.rstrip('/') != settings.LOCAL_NODE_URL.rstrip('/'):
                inbox_url = parent_node.id.rstrip('/') + '/inbox'
                auth = None
                if getattr(parent_node, 'auth_user', None):
                    auth = (parent_node.auth_user, parent_node.auth_pass)

                resp = requests.post(
                    inbox_url,
                    json=comment_object,
                    auth=auth,
                    headers={'Content-Type': 'application/json'},
                    timeout=5,
                )
                if not (200 <= resp.status_code < 300):
                    print(f"Failed to send comment to parent node {inbox_url}: {resp.status_code}")

        except Exception as e:
            # never fail the API call because of network issues; comment was saved locally
            print(f"Error when attempting to forward comment: {e}")

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, entry_id):
        """
        TODO: DELETE comments for an entry because the API is kindof buggy
        """
        entry_id = unquote(entry_id).rstrip("/")  # decode FQID back to full URL

        entry = get_object_or_404(Entry, entry_id)

        comment_id = request.query_params.get('id', None)

        if comment_id:
            deleted, _ = Comment.objects.filter(id=comment_id, entry=entry).delete()
            if deleted:
                print(f"DEBUG: Deleted specific comment {comment_id}")
                return Response({'deleted': comment_id}, status=status.HTTP_204_NO_CONTENT)
            print(f"DEBUG: Comment not found: {comment_id}")
            return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            deleted, _ = Comment.objects.filter(entry=entry).delete()
            print(f"DEBUG: Deleted {deleted} comments for entry {entry_id}")
            return Response({'deleted_count': deleted}, status=status.HTTP_204_NO_CONTENT)

# @swagger_auto_schema(
#     method='GET',
#     operation_summary='Retrieve Node information',
#     operation_description='Returns node metadata by id',
#     responses={
#         200: openapi.Response(description="OK"),
#         404: openapi.Response(description="Not found"),
#         400: openapi.Response(description="Bad request"),
#     }
# )
class NodeAPIView(APIView):
    """
    This API view handles GET requests to retrieve node data by ID.
    - GET /api/node/<id>/ will then retrieve node data
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        node = get_object_or_404(Node, id)
        return Response(NodeSerializer(node).data, status=status.HTTP_200_OK)

class FollowAPIView(APIView):
    """
    This API view handles GET requests to retrieve follow data by ID.
    - GET /api/follow/<id>/ will then retrieve follow data
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        follow = get_object_or_404(Follow, id)
        return Response(NodeSerializer(follow).data, status=status.HTTP_200_OK)

class LikeAPIView(APIView):
    """
    This API view handles GET requests to retrieve like data by ID.
    - GET /api/like/<id>/ will then retrieve like data
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, entry_id):
        like = get_object_or_404(Like, entry_id)
        likes_qs = Like.objects.filter(object=entry_id).order_by('-published')
        try:
            page_size = int(request.query_params.get('size', 5))
        except Exception:
            page_size = 5
        try:
            page_number = int(request.query_params.get('page', 1))
        except Exception:
            page_number = 1

        paginator = Paginator(likes_qs, page_size)
        page_obj = paginator.get_page(page_number)

        serialized = LikeSerializer(page_obj.object_list, many=True).data

        host = request.build_absolute_uri('/').rstrip('/')
        collection_id = f"{host}/api/Entry/{entry_id}/likes/"

        collection = {
            "type": "likes",
            "id": collection_id,
            "web": collection_id.replace('/api/', '/'),
            "page_number": page_number,
            "size": page_size,
            "count": paginator.count,
            "src": serialized,
        }

        return Response(LikeSerializer(like).data, status=status.HTTP_200_OK)


class CommentLikeAPIView(APIView):
    """GET/POST a paginated list of likes for a Comment object (by Comment FQID or suffix).

    GET returns an ActivityPub-like collection. POST creates a Like.
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, comment_id):
        # comment_id may be a full FQID or a UUID suffix
        comment_id = unquote(comment_id).rstrip('/')

        likes_qs = Like.objects.filter(object=comment_id).order_by('-published')

        # Pagination parameters
        try:
            page_size = int(request.query_params.get('size', 5))
        except Exception:
            page_size = 5
        try:
            page_number = int(request.query_params.get('page', 1))
        except Exception:
            page_number = 1

        paginator = Paginator(likes_qs, page_size)
        page_obj = paginator.get_page(page_number)

        serialized = LikeSerializer(page_obj.object_list, many=True).data

        host = request.build_absolute_uri('/').rstrip('/')
        collection_id = f"{host}/api/Comment/{comment_id}/likes/"

        collection = {
            "type": "likes",
            "id": collection_id,
            "web": collection_id.replace('/api/', '/'),
            "page_number": page_number,
            "size": page_size,
            "count": paginator.count,
            "src": serialized,
        }

        return Response(collection, status=status.HTTP_200_OK)

    def post(self, request, comment_id):
        """Create a Like targeting the Comment identified by `comment_id`.

        Idempotent: if the same author already liked the object, return the existing like.
        """
        comment_id = unquote(comment_id).rstrip('/')

        # resolve comment by exact FQID or suffix
        try:
            comment = Comment.objects.get(id=comment_id)
        except Comment.DoesNotExist:
            try:
                comment = Comment.objects.get(id__endswith=comment_id)
            except Comment.DoesNotExist:
                return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)

        actor = request.user
        # check for existing like by this author on this object
        existing = Like.objects.filter(author=actor, object=comment.id).first()
        if existing:
            return Response(LikeSerializer(existing).data, status=status.HTTP_200_OK)
        # FQID for like
        like_id = f"{settings.SITE_URL.rstrip('/')}/api/authors/{actor.uuid}/liked/{uuid.uuid4()}"

        like = Like(id=like_id, author=actor, object=comment.id, published=timezone.now())
        like.save()

        # TODO: enqueue fan-out to remote inboxes (send Create activity containing this Like)

        return Response(LikeSerializer(like).data, status=status.HTTP_201_CREATED)

class AuthorFriendsView(APIView):
    """
    This API view handles GET requests to retrieve an author's friends (mutual followers).
    - GET /api/Author/<author_id>/friends/ will then retrieve a list of friends
    """
    def get(self, request, author_id):
        author = get_object_or_404(Author, id=author_id)

        # Get all accepted follow relationships
        outgoing = Follow.objects.filter(actor=author, state="ACCEPTED").values_list("object", flat=True)
        incoming = Follow.objects.filter(object=author.id, state="ACCEPTED").values_list("actor__id", flat=True)

        # Mutual follows = both in outgoing and incoming
        mutual_ids = set(outgoing).intersection(incoming)
        mutuals = Author.objects.filter(id__in=mutual_ids)

        serializer = AuthorSerializer(mutuals, many=True)
        return Response(serializer.data)