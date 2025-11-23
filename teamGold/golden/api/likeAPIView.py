
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
from golden.models import Author, Entry, Comment, Like, Node
from golden.services import generate_like_fqid, paginate
from golden.distributor import distribute_activity
from golden.activities import create_like_activity

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# SERIALIZERS IMPORTS
from golden.serializers import (
    MinimalAuthorSerializer, LikeSerializer, 
)

class LikeAPIView(APIView):
    """
    This API view handles GET and POST requests for Entry likes.
    - GET /api/like/<id>/ will then retrieve like data
    - POST /Entry/<entry_id>/like
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]
    #! WIP
    def get(self, request, entry_id):
        # Normalize entry_id and build queryset of Likes targeting that entry FQID
        entry_id = unquote(entry_id).rstrip('/')
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

        # Match deepskyblue spec format
        collection = {
            "type": "likes",
            "object": entry_id,  # Add object field to match spec
            "count": paginator.count,
            "src": serialized,
        }

        # Return the collection
        return Response(collection, status=status.HTTP_200_OK)

    
    @swagger_auto_schema(
        operation_summary="Liking an entry",
        operation_description="User likes an entry and if the host is remote, send it to the remote inbox." \
        "If it is local, send like notification to all followers of current user." \
        "support for url pattern api/Entry/<path:entry_id>/likes/",
        responses={
            201: openapi.Response("Like created"),
            404: openapi.Response("Entry/Author not found"),
            400: openapi.Response("Bad request"),
        }
    )
    def post(self, request, entery_id):
        if not request.content_type or 'application/json' not in request.content_type:
            return Response({'detail': 'Content-Type must be application/json'}, status=status.HTTP_400_BAD_REQUEST)
        
      
        entry_id = unquote(entry_id).rstrip("/") # decode fqid to url

        # we need to look it up on our local database or resolve it to a remote author
        # TODO we might need support for remote authors (but this user is technically local to its own node sooo)
        like_author = get_object_or_404(Author, id=request.user.id)# author will be a nested object

        entry = get_object_or_404(id=entry_id)
        data = request.data.copy()
        # serializer set up
        data['entry'] = entry.id
        data['author'] = request.user.uid
        like_id = generate_like_fqid(like_author, entry)
        data['id'] = like_id
        data['published'] = timezone.now().isoformat()
        
        data.pop('author', None)
        serializer = LikeSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        like = serializer.save(entry=entry, liked_author=request.user, liking_author=None)
        entry.save(update_fields=['likes'])

        # Use distribute_activity to handle both local and remote delivery
        # This automatically routes to the correct inbox (local DB or remote API)
        activity = create_like_activity(like_author, entry.id)
        distribute_activity(activity, actor=like_author)

        # Return the newly created comment as nested JSON (includes nested author)
        serialized = LikeSerializer(like)
        return Response(serialized.data, status=status.HTTP_201_CREATED)


class CommentLikeAPIView(APIView):
    """
    PURPOSE: API view handles POST requests for a comments' likes
    METHODS:
        POST api/Entry/<path:entry_id>/likes/
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

      
    @swagger_auto_schema(
        operation_summary='Adding a like to a comment',
        operation_description='User likes a comment, and the like will either be sent to the inbox of the remote node or the ' \
        'inboxes of followers of the user' \
        ' Idempotent: if the same author already liked the object, return 200',
        request_body=LikeSerializer,
        responses={
            201: openapi.Response(description="Comment Like Created",
                examples={"application/json"}),
            201: openapi.Response(description="Comment Like already exists"),
            404: openapi.Response(description="Not found"),
            400: openapi.Response(description="Comment Like creation failure"),
        }
    )
    def post(self, request, entry_id):
        if not request.content_type or 'application/json' not in request.content_type:
            return Response({'detail': 'Content-Type must be application/json'}, status=status.HTTP_400_BAD_REQUEST)
        
        entry_id = unquote(entry_id).rstrip("/") # decode fqid to url
        print("DEBUG entry_id: ", entry_id, flush=True)

        # Try to find entry both with and without trailing slash (tests sometimes create one or the other)
        entry = Entry.objects.filter(id=entry_id).first()
        if not entry:
            entry = Entry.objects.filter(id=entry_id + '/').first()
        if not entry:
            return Response({'detail': 'Entry not found'}, status=status.HTTP_404_NOT_FOUND)
        print("DEBUG entry found")
        
        like_author = get_object_or_404(Author, id=request.user.id)# author will be a nested object
        print("DEBUG user found")

        # check to see if the like already exists
        has_liked = Like.objects.filter(author=like_author, object=entry_id)
        if has_liked:
            like = Like.objects.get(author=like_author, object=entry_id)
            return Response(like, status=status.HTTP_200_OK)
        
        # server side fields
        data = request.data.copy()
        data['entry'] = entry.id
        data['type'] = 'like'
        like_id = generate_like_fqid(like_author, entry)
        data['id'] = like_id
        data['published'] = timezone.now().isoformat()

        # Remove any nested author payload — we resolve the author server-side
        data.pop('author', None)
        print("DEBUG data (sanitized):", data, flush=True)
        serializer = LikeSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        like = serializer.save(entry=entry, author=like_author)
   
        # Use distribute_activity to handle both local and remote delivery
        # This automatically routes to the correct inbox (local DB or remote API)
        activity = create_like_activity(like_author, entry.id)
        distribute_activity(activity, actor=like_author)

        # Return the newly created comment as nested JSON (includes nested author)
        serialized = LikeSerializer(like)
        return Response(serialized.data, status=status.HTTP_201_CREATED)
    