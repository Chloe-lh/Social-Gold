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
from golden.services import generate_comment_fqid, resolve_or_create_author, paginate
from golden.utils import post_to_remote_inbox, get_or_create_foreign_author

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# SERIALIZERS IMPORTS
from golden.serializers import (
    AuthorSerializer, EntrySerializer, NodeSerializer,
    FollowSerializer, LikeSerializer, CommentSerializer, EntryImageSerializer,
    EntryInboxSerializer, CommentsInfoSerializer, LikeInboxSerializer,
    FollowRequestInboxSerializer
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
        node = get_object_or_404(Node, id) # ! IS THIS NOT id=id?
        return Response(NodeSerializer(node).data, status=status.HTTP_200_OK)

class FollowAPIView(APIView):
    """
    This API view handles GET requests to retrieve follow data by ID.
    - GET /api/follow/<id>/ will then retrieve follow data
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        follow = get_object_or_404(Follow, id) # ! IS THIS NOT id=id?
        return Response(NodeSerializer(follow).data, status=status.HTTP_200_OK)

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
    
class InboxView(APIView):
    def get(self, request, author_id): pass
    def post(self, request): pass

# ! HELPER FUNCTIONS
def distribute_entry_activity(entry, action="create"):
    """
    Distribute entry to remote followers based on visibility.
    action: "create", "update", or "delete"
    """
    author = entry.author
    
    followers = Follow.objects.filter(object=author.id, state="ACCEPTED").select_related('actor')

    for follow in followers:
        follower = follow.actor
        
        if follower.host and follower.host.startswith(settings.SITE_URL):
            continue
        
        should_send_entry = False
        if entry.visibility in ["PUBLIC", "UNLISTED"]:
            should_send_entry = True
        elif entry.visibility == "FRIENDS":
            # Only send to friends (mutual followers)
            if follower in author.friends:
                should_send_entry = True
        
        if should_send_entry:
            send_entry_activity(follower, entry, action)

# ! HELPER FUNCTIONS
def send_entry_activity(recipient, entry, action):
    try:
        entry_data = EntryInboxSerializer(entry).data
        
        if action == "delete":
            entry_data['visibility'] = "DELETED"
            activity = {
                "type": "Update",
                "actor": {"id": entry.author.id},
                "object": entry_data
            }
        elif action == "update":
            activity = {
                "type": "Update",
                "actor": {"id": entry.author.id},
                "object": entry_data
            }
        else: 
            activity = {
                "type": "Create",
                "actor": {"id": entry.author.id},
                "object": entry_data
            }

        inbox_url = recipient.id.rstrip('/') + '/inbox/'
        node = Node.objects.filter(host__icontains=urlparse(recipient.id).netloc).first()
        post_to_remote_inbox(inbox_url, activity, node=node)
        
    except Exception as e:
        print(f"Failed to send {recipient.id}: {e}")