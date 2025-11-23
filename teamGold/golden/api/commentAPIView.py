
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# DJANGO IMPORTS
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
from django.core.paginator import Paginator
import uuid
import requests
import json
from urllib.parse import quote, unquote, urlparse

# PYTHON IMPORTS
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import logging

# LOCAL IMPORTS
from golden.models import Author, Entry, Comment, Like, Follow, Node
from golden.services import generate_comment_fqid, paginate, fqid_to_uuid, get_remote_node_from_fqid, notify
from golden.distributor import distribute_activity
from golden.activities import create_comment_activity

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# SERIALIZERS IMPORTS
from golden.serializers import CommentSerializer, MinimalAuthorSerializer


class EntryCommentAPIView(APIView):
    """
   
    PURPOSE: This API view handles GET, POST requests for an entry's comments
    METHODS:
        POST /api/authors/<AUTHOR_SERIAL>/entries/<ENTRY_SERIAL>/comments is for creating a new comment
        GET  /api/entries/<path:entry_fqid>/comments/ - get all comments on entry
        GET service/api/authors/{AUTHOR_SERIAL}/entries/{ENTRY_SERIAL}/comments - get all comments on entry
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary='Gets all comments for an entry',
        operation_description='Will return JSON data representing a list of Comment Objects./' \
        'Every comment has a nested author object. This method accepts URLS specifying entry and author.' \
        'Body is always a comments object',
        responses={
            200: openapi.Response(description="Comments found"),
            404: openapi.Response(description="Comment Not found"),
        }
    )
    def get(self, request, entry_id=None, entry_fqid=None, *args, **kwargs):
        """Return a comments collection for an entry.

        Accepts either:
        - path param named `entry_id` or `entry_fqid` (URL-encoded FQID), or
        - kwargs keys like `entry_serial` (author+entry alias).

        Behavior:
        - If the entry exists locally, return stored comments (paginated).
        - If the entry is not local but belongs to a known remote Node, fetch from that node's
          `/api/entries/{ENTRY_FQID}/comments/` endpoint and proxy the result.
        - Otherwise return 404.
        The response body is a "comments" collection object with `type`, `id`, `size`, and `items`.
        """
        print("ENTER EntryCommentAPIView.get", flush=True)
  
        raw = entry_id or entry_fqid or kwargs.get('entry_serial') or kwargs.get('entry_fqid')
        if not raw:
            return Response({'detail': 'entry id required'}, status=status.HTTP_400_BAD_REQUEST)

        entry_fqid = unquote(raw).rstrip('/')
        print("DEBUG entry_fqid: %s ", entry_fqid, flush=True)

        # Try local lookup first
        try:
            entry = Entry.objects.get(id=entry_fqid)
        except Entry.DoesNotExist:
            entry = None

        # If local, return paginated local comments
        if entry:
            qs = Comment.objects.filter(entry_id=entry.id).order_by('-published')
            page_obj = paginate(request, qs)
            items = CommentSerializer(page_obj.object_list, many=True).data

            # Match deepskyblue spec format
            collection = {
                "type": "comments",
                "page": page_obj.number,
                "size": page_obj.paginator.per_page,
                "count": qs.count(),
                "src": items,  # Changed from "items" to "src" to match spec
            }

            # add simple pagination links if applicable
            if page_obj.has_next():
                next_page = page_obj.next_page_number()
                collection['next'] = f"{request.build_absolute_uri('?page=' + str(next_page))}"
            if page_obj.has_previous():
                prev_page = page_obj.previous_page_number()
                collection['prev'] = f"{request.build_absolute_uri('?page=' + str(prev_page))}"

            return Response(collection, status=status.HTTP_200_OK)

        # attempt to find a remote node and find its comments endpoint
        remote_node = get_remote_node_from_fqid(entry_fqid)
        if remote_node and remote_node.id.rstrip('/') != settings.LOCAL_NODE_URL.rstrip('/'):
            try:
                remote_comments_url = remote_node.id.rstrip('/') + '/api/entries/' + quote(entry_fqid, safe='') + '/comments/'
                resp = requests.get(
                    remote_comments_url,
                    auth=(remote_node.auth_user, remote_node.auth_pass) if getattr(remote_node, 'auth_user', None) else None,
                    headers={'Accept': 'application/json'},
                    timeout=5,
                )
                if resp.status_code == 200:
                    return Response(resp.json(), status=status.HTTP_200_OK)
                elif resp.status_code == 404:
                    return Response({'detail': 'Remote entry not found'}, status=status.HTTP_404_NOT_FOUND)
                else:
                    return Response({'detail': 'Failed to fetch remote comments'}, status=status.HTTP_502_BAD_GATEWAY)
            except Exception as e:
                return Response({'detail': f'Failed to fetch remote comments: {e}'}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({'detail': 'Entry not found'}, status=status.HTTP_404_NOT_FOUND)

    '''
    steps:
        1. create serializer data
        2. create Comment activity (object) to send
        3. parse entry_id to get node
        4. check if host is local or remote
            5. if remote - send to remote nodes inbox (current url)
            6. if local - send to all followers of Author using notify()
    '''

    @swagger_auto_schema(
        operation_summary='Adding a comment to an entry',
        operation_description='Client sends a POST request to comment on an entry',
        request_body=CommentSerializer,
        responses={
            201: openapi.Response(description="Comment Created",
                examples={"application/json"}),
            404: openapi.Response(description="Not found"),
            400: openapi.Response(description="Comment creation failure"),
        }
    )
    def post(self, request, entry_id):
        print("ENTER EntryCommentAPIView.post", flush=True)
        entry_id = unquote(entry_id).rstrip("/") # decode fqid to url
        print("DEBUG entry_id: ", entry_id, flush=True)

        # Try to find entry both with and without trailing slash (tests sometimes create one or the other)
        entry = Entry.objects.filter(id=entry_id).first()
        if not entry:
            entry = Entry.objects.filter(id=entry_id + '/').first()
        if not entry:
            return Response({'detail': 'Entry not found'}, status=status.HTTP_404_NOT_FOUND)
        print("DEBUG entry found")
        # Accept application/json even when charset is present
        if not request.content_type or 'application/json' not in request.content_type:
            return Response({'detail': 'Content-Type must be application/json'}, status=status.HTTP_400_BAD_REQUEST)
        
        # server side fields
        data = request.data.copy()
        print("DEBUG request.user.id=", request.user.id)
        # we need to look it up on our local database or resolve it to a remote author
        author = get_object_or_404(Author, id=request.user.id)# author will be a nested object
        print("DEBUG user found")
        data = request.data.copy()
        data['entry'] = entry.id
        data['type'] = 'comment'
        comment_id = generate_comment_fqid(author, entry)
        data['id'] = comment_id
        data['published'] = timezone.now().isoformat()

        # Remove any nested author payload — we resolve the author server-side
        data.pop('author', None)
        print("DEBUG data (sanitized):", data, flush=True)
        serializer = CommentSerializer(data=data)
        if not serializer.is_valid():
            print("DEBUG serializer.errors:", serializer.errors, flush=True)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        comment = serializer.save(entry=entry, author=author)
        print("DEBUG comment saved id=", getattr(comment, 'id', None), flush=True)

        # Use distribute_activity to handle both local and remote delivery
        # This automatically routes to the correct inbox (local DB or remote API)
        activity = create_comment_activity(author, entry, comment)
        distribute_activity(activity, actor=author)
        
        print("DEBUG: Comment activity distributed", flush=True)

        # Return the newly created comment as nested JSON (includes nested author)
        serialized = CommentSerializer(comment)
        return Response(serialized.data, status=status.HTTP_201_CREATED)
    

'''
    PURPOSE: get a single comment on a post
    METHODS: 
        GET  /api/authors/<AUTHOR_SERIAL>/entries/<ENTRY_SERIAL>/comment/{REMOTE_COMMENT_FQID} - get comment from remote node
'''
class SingleCommentAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary = "Get a single comment on an entry",
        operation_description = "Retrieves a single comment using author and entry. " \
        "Supports URL api/authors/<str:author_serial>/entries/<str:entry_serial>/comments/<path:comment_fqid>"\
        "accepts author as FQID string or nested object",
        responses={
            200: openapi.Response("Comment found"),
            404: openapi.Response("Comment not found"),
        }
    )
    def get(self, request):
        # decode remote/local fqid
        comment_fqid = unquote(request.build_absolute_uri())
        comment_uid = fqid_to_uuid(comment_fqid)

        remote_node = get_remote_node_from_fqid(comment_fqid)
        if not remote_node: # make it local
            comment = get_object_or_404(Comment,id=comment_uid)
            serializer = CommentSerializer(comment)
            return Response(serializer.data, status=status.HTTP_200_OK)            
        else: # remote comment - get from remote node
            try:
                res = requests.get(
                    comment_fqid,
                    auth=(remote_node.auth_user, remote_node.auth_pass),
                    headers={'Accept':'application/json'}
                )
                if res.status_code==200:
                    return Response(res.json(), status=status.HTTP_200_OK)
            except Exception as e:
                return Response(
                    {"detail":f"Failed to fetch remote comment: {comment_fqid}"}
                )
