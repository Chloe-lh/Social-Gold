
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
    
    @swagger_auto_schema(
        operation_summary='Gets all likes for an entry',
        operation_description='Will return JSON data representing a list of Like Objects./' \
        'Every like has a nested author object. This method accepts URLS specifying entry and author.' \
        'Body is always a comments object',
        responses={
            200: openapi.Response(description="Comments found"),
            404: openapi.Response(description="Comment Not found"),
        }
    )
    def get(self, request, author_serial=None, entry_serial=None, *args, **kwargs):
        """Return a comments collection for an entry.

        Accepts either:
        - path param named `entry_id` or `entry_fqid` (URL-encoded FQID), or
        - kwargs keys like `entry_serial` (author+entry alias).

        Queries (optional):
        - page param denotes the page number; default 1
        - size denotes the page size; default 10

        Behavior:
        - If the entry exists locally, return stored comments (paginated).
        - If the entry is not local but belongs to a known remote Node, fetch from that node's
          `/api/entries/{ENTRY_FQID}/comments/` endpoint and proxy the result.
        - Otherwise return 404.
        The response body is a "comments" collection object with `type`, `id`, `size`, and `items`.
        """
        print("ENTER EntryLikeAPIView.get", flush=True)
  
        if not entry_serial:
            return Response({'detail': 'entry id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            entry = Entry.objects.get(id__contains=entry_serial)
        except Entry.DoesNotExist:
            return Response({'detail': 'entry not found'}, status=status.HTTP_404_NOT_FOUND)

        # Make sure the author of the entry is the author specifed if author serial is provided
        if author_serial and author_serial not in entry.author.id:
            return Response({'detail': 'entry not found by specified author'}, status=status.HTTP_404_NOT_FOUND)

        # return paginated local comments
        qs = Like.objects.filter(entry_id=entry.id).order_by('-published')
        page_obj = paginate(request, qs)
        items = LikeSerializer(page_obj.object_list, many=True).data

        collection = {
            "type": "comments",
            "id": request.build_absolute_uri(),
            "size": qs.count(),
            "items": items,
        }

        # add simple pagination links if applicable
        if page_obj.has_next():
            next_page = page_obj.next_page_number()
            collection['next'] = f"{request.build_absolute_uri('?page=' + str(next_page))}"
        if page_obj.has_previous():
            prev_page = page_obj.previous_page_number()
            collection['prev'] = f"{request.build_absolute_uri('?page=' + str(prev_page))}"

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
    