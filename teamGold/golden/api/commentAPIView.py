
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
from golden.models import Author, Entry, Comment, Like, Follow, Node, EntryImage
from golden.services import generate_comment_fqid, resolve_or_create_author, paginate, fqid_to_uuid, get_remote_node_from_fqid

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# SERIALIZERS IMPORTS
from golden.serializers import (
    AuthorSerializer, EntrySerializer, NodeSerializer,
    FollowSerializer, LikeSerializer, CommentSerializer, EntryImageSerializer
)

class EntryCommentAPIView(APIView):
    """
   
    PURPOSE: This API view handles GET, POST, PUT, and DELETE requests for an entry's comments
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

#! WIP
    # @swagger_auto_schema(
    #     operation_summary='Adding a comment to an entry',
    #     operation_description='Client sends a POST request to comment on an entry',
    #     request_body=CommentSerializer,
    #     responses={
    #         201: openapi.Response(description="Comment Created",
    #             examples={"application/json"}),
    #         404: openapi.Response(description="Not found"),
    #         400: openapi.Response(description="Comment creation failure"),
    #     }
    # )
    # def post(self, request, entry_id):
    #     logger = logging.getLogger(__name__)
    #     logger.debug("ENTER EntryCommentAPIView.post")
    #     entry_id = unquote(entry_id).rstrip("/") # decode fqid to url
    #     logger.debug("DEBUG entry_id=%s", entry_id)
    #     entry = get_object_or_404(Entry, id=entry_id)
       
    #     if request.content_type != 'application/json':
    #         return Response({'detail': 'Content-Type must be application/json'}, status=status.HTTP_400_BAD_REQUEST)
        
    #     # server side fields
    #     data = request.data.copy()
    #     # author will be a nested object
    #     # we need to look it up on our local database or resolve it to a remote author
    #     incoming = request.data.get('author')   # could be str, dict, or missing
    
    #     try:
    #         author = resolve_or_create_author(incoming, create_if_missing = True)
    #     except Author.DoesNotExist:
    #         return Response({'detail':'Author not found'}, status=400)

    #     data["type"] = "comment"
    #     data["entry"] = entry.id #id == fqid
    #     # generate FQID (service expects (author, entry))
    #     # e.g. "id":"http://nodeaaaa/api/authors/<author_uuid>/commented/<uuid>"
    #     comment_id = generate_comment_fqid(author, entry)
    #     data["id"] = comment_id
    #     data["published"] = timezone.now().isoformat()


    #     # create comment instance in database
    #     # serializer maps data->json fields
    #     try:
    #         logger.debug("DEBUG: Comment payload (data) = %s", json.dumps(data, indent=2, default=str))
    #     except Exception:
    #         # fallback if data contains non-JSONable objects
    #         logger.debug("DEBUG: Comment payload (repr) = %s", repr(data))

    #     serializer = CommentSerializer(data=data)
    #     if serializer.is_valid():
    #         comment = serializer.save(
    #             entry=entry,
    #             author=author,
    #             content_type=data["content_type"],
    #             content=data["content"]
    #         )
        
    #     # Create the Comment directly to avoid nested-write serializer complexity.
    #     comment_data = {
    #         "type":"comment",
    #         "author":AuthorSerializer(request.user).data,
    #         "comment": comment.content,
    #         "contentType": comment.content_type,
    #         "published": comment.published_at.isoformat(),
    #         "id": f"{request.build_absolute_uri()}/comments/{comment_id}"
    #     }
        

    #     # if the entry author is remote, attempt to POST the comment
    #     # to that node's inbox. Determine the parent node by matching the author's host.
    #     try:
    #         # Serialize the saved comment for sending
    #         comment_object = CommentSerializer(comment).data

    #         # parse host from the entry's author's id (FQID)
    #         actor_id = getattr(entry.author, 'id', None)
    #         if actor_id:
    #             parsed = urlparse(actor_id)
    #             actor_host = f"{parsed.scheme}://{parsed.netloc}"
    #             parent_node = Node.objects.filter(id__startswith=actor_host).first()
    #         else:
    #             parent_node = None

    #         if parent_node and parent_node.id.rstrip('/') != settings.LOCAL_NODE_URL.rstrip('/'):
    #             inbox_url = parent_node.id.rstrip('/') + '/inbox'
    #             auth = None
    #             if getattr(parent_node, 'auth_user', None):
    #                 auth = (parent_node.auth_user, parent_node.auth_pass)

    #             # Debug
    #             try:
    #                 logger.debug("DEBUG: Forwarding comment to parent node %s", parent_node.id)
    #                 logger.debug("DEBUG: inbox_url=%s auth=%s", inbox_url, 'yes' if auth else 'no')
    #                 logger.debug("DEBUG: comment payload: %s", json.dumps(comment_object, indent=2, default=str))
    #             except Exception:
    #                 logger.debug("DEBUG: comment payload repr: %s", repr(comment_object))

    #             resp = requests.post(
    #                 inbox_url,
    #                 json=comment_object,
    #                 auth=auth,
    #                 headers={'Content-Type': 'application/json'},
    #                 timeout=5,
    #             )
    #             # Debug
    #             try:
    #                 logger.debug("DEBUG: Remote response status=%s", resp.status_code)
    #                 logger.debug("DEBUG: Remote response text=%s", resp.text)
    #             except Exception:
    #                 logger.debug("DEBUG: Remote response (non-serializable)")

    #             if not (200 <= resp.status_code < 300):
    #                 logger.debug("Failed to send comment to parent node %s: %s", inbox_url, resp.status_code)

    #     except Exception as e:
    #         # never fail the API call because of network issues; comment was saved locally
    #         logger.exception("Error when attempting to forward comment: %s", e)

    #     # Return the newly created comment as nested JSON (includes nested author)
    #     serialized = CommentSerializer(comment)
    #     return Response(serialized.data, status=status.HTTP_201_CREATED)
    
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

class AuthorCommentedAPIView(APIView):
    '''
    GET /api/authors/<author_id>/commented - returns paginated list of comments made by the authenticated author
       - this applies to local and remote entries
       - we filter by PUBLIC and UNLISTED
    POST /api/authors/<author_id>/commented - creates a comment as authenticated author
    '''
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_description='Retreives all comments made by a single author',
        responses={
            200: openapi.Response(description="Comment found"),
            404: openapi.Response(description="Comment Not found"),
        }
    )
    def get(self,request,author_id): pass
    #     author_id = unquote(author_id).rstrip('/')
    #     local_base = settings.LOCAL_NODE_URL.rstrip('/')

    #     # look up locally
    #     try:
    #         author = Author.objects.get(pk=id)
    #     except Author.DoesNotExist:
    #         return Response(status=status.HTTP_404_NOT_FOUND)
    #     comment_list = Comment.objects.filter(author_id = author.d).select_related('entry').order_by('-published')

    #     #filter comments and determine if in node
    #     allowed = []
    #     for c in comment_list:
    #         try:
    #             parsed = urlparse(c.entry.id)
    #             host_base = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
    #         except Exception:
    #             host_base = ''
            
    #     if entry_base == local_base:

            
    #         if host_base == local_base:
    #             allowed.append(c)
    #         else:
    #             if getattr(c.entry, 'visibility', '') in ('PUBLIC', 'UNLISTED'):
    #                 allowed.append(c)

    #     page_obj = paginate(request, comment_list)
    #     serialized = CommentSerializer(page_obj.object_list, many=True).data
    #     host = request.build_absolute_uri('/')
      
    #     # for comment in comment_list{
    #     #     "type": "comments",
    #     #     "id": co
            
    #     # }