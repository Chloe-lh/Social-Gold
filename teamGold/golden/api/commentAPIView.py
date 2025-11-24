
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
from urllib.parse import unquote

# PYTHON IMPORTS
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# LOCAL IMPORTS
from golden.models import Author, Entry, Comment
from golden.services import generate_comment_fqid, paginate, fqid_to_uuid, get_remote_node_from_fqid
from golden.distributor import distribute_activity
from golden.activities import create_comment_activity

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# SERIALIZERS IMPORTS
from golden.serializers import CommentSerializer, MinimalAuthorSerializer


class EntryCommentAPIView(APIView):
    """
    API view for handling comments on a specific entry.

    URL patterns supported:
    - GET /api/entries/<ENTRY_FQID>/comments/ - list comments for an entry
    - GET /api/authors/<AUTHOR_SERIAL>/entries/<ENTRY_SERIAL>/comments - list comments by author and entry
    - POST /api/authors/<AUTHOR_SERIAL>/entries/<ENTRY_SERIAL>/comments - create a new comment on an entry
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary='List all comments for an entry',
        operation_description=(
            "Returns a paginated list of Comment objects for a given entry. "
            "Each comment includes nested author information. "
            "Optional query parameters:\n"
            "- `page`: page number (default 1)\n"
            "- `size`: page size (default 10)"
        ),
        responses={
            200: openapi.Response(description="Comments retrieved successfully"),
            404: openapi.Response(description="Entry not found"),
            400: openapi.Response(description="Bad request"),
        }
    )
    def get(self, request, author_serial=None, entry_serial=None, *args, **kwargs):
        if not entry_serial:
            return Response({'detail': 'entry id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            entry = Entry.objects.get(id__contains=entry_serial)
        except Entry.DoesNotExist:
            return Response({'detail': 'entry not found'}, status=status.HTTP_404_NOT_FOUND)

        if author_serial and author_serial not in entry.author.id:
            return Response({'detail': 'entry not found by specified author'}, status=status.HTTP_404_NOT_FOUND)

        qs = Comment.objects.filter(entry_id=entry.id).order_by('-published')
        page_obj = paginate(request, qs)
        items = CommentSerializer(page_obj.object_list, many=True).data

        collection = {
            "type": "comments",
            "id": request.build_absolute_uri(),
            "size": qs.count(),
            "items": items,
        }

        if page_obj.has_next():
            next_page = page_obj.next_page_number()
            collection['next'] = f"{request.build_absolute_uri('?page=' + str(next_page))}"
        if page_obj.has_previous():
            prev_page = page_obj.previous_page_number()
            collection['prev'] = f"{request.build_absolute_uri('?page=' + str(prev_page))}"

        return Response(collection, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_summary='Create a new comment for an entry',
        operation_description='Posts a comment to a specified entry. Server automatically sets author, ID, and timestamp.',
        request_body=CommentSerializer,
        responses={
            201: openapi.Response(description="Comment created successfully"),
            400: openapi.Response(description="Invalid request or serializer errors"),
            404: openapi.Response(description="Entry or Author not found"),
        }
    )
    def post(self, request, entry_id):
        entry_id = unquote(entry_id).rstrip("/")
        entry = Entry.objects.filter(id=entry_id).first() or Entry.objects.filter(id=entry_id + '/').first()
        if not entry:
            return Response({'detail': 'Entry not found'}, status=status.HTTP_404_NOT_FOUND)

        if not request.content_type or 'application/json' not in request.content_type:
            return Response({'detail': 'Content-Type must be application/json'}, status=status.HTTP_400_BAD_REQUEST)

        author = get_object_or_404(Author, id=request.user.id)
        data = request.data.copy()
        data['entry'] = entry.id
        data['type'] = 'comment'
        data['id'] = generate_comment_fqid(author, entry)
        data['published'] = timezone.now().isoformat()
        data.pop('author', None)

        serializer = CommentSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        comment = serializer.save(entry=entry, author=author)
        activity = create_comment_activity(author, entry, comment)
        distribute_activity(activity, actor=author)

        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class SingleCommentAPIView(APIView):
    """
    API view to retrieve a single comment by FQID.

    URL pattern:
    - GET /api/authors/<AUTHOR_SERIAL>/entries/<ENTRY_SERIAL>/comments/<COMMENT_FQID>
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Retrieve a single comment",
        operation_description=(
            "Fetches a single comment using the provided author, entry, and comment FQID. "
            "If the comment is remote, it fetches from the remote node."
        ),
        responses={
            200: openapi.Response(description="Comment found"),
            404: openapi.Response(description="Comment not found or remote fetch failed"),
        }
    )
    def get(self, request):
        comment_fqid = unquote(request.build_absolute_uri())
        comment_uid = fqid_to_uuid(comment_fqid)
        remote_node = get_remote_node_from_fqid(comment_fqid)

        if not remote_node:
            comment = get_object_or_404(Comment, id=comment_uid)
            serializer = CommentSerializer(comment)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            try:
                res = requests.get(
                    comment_fqid,
                    auth=(remote_node.auth_user, remote_node.auth_pass),
                    headers={'Accept':'application/json'}
                )
                if res.status_code == 200:
                    return Response(res.json(), status=status.HTTP_200_OK)
            except Exception:
                return Response({"detail": f"Failed to fetch remote comment: {comment_fqid}"}, status=status.HTTP_404_NOT_FOUND)


class CommentedAPIView(APIView):
    """
    API view to manage and retrieve comments authored by a user.

    URL patterns supported:
    - GET /api/authors/{AUTHOR_SERIAL}/commented - list comments by author
    - POST /api/authors/{AUTHOR_SERIAL}/commented - post a new comment
    - GET /api/commented/{COMMENT_FQID} - retrieve a specific comment
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Create a comment on behalf of the user",
        operation_description="Posts a new comment for the authenticated user to a specified entry.",
        request_body=CommentSerializer,
        responses={
            201: openapi.Response(description="Comment created successfully"),
            400: openapi.Response(description="Invalid request or serializer errors"),
            404: openapi.Response(description="Entry or Author not found"),
        }
    )
    def post(self, request, author_serial):
        entry_id = request.data.get("entry")
        if not entry_id:
            return Response({'detail': "'entry' field is required"}, status=status.HTTP_400_BAD_REQUEST)

        entry = Entry.objects.filter(id=entry_id).first() or Entry.objects.filter(id=entry_id + '/').first()
        if not entry:
            return Response({'detail': 'Entry not found'}, status=status.HTTP_404_NOT_FOUND)

        author = get_object_or_404(Author, id=request.user.id)
        data = request.data.copy()
        data['entry'] = entry.id
        data['type'] = 'comment'
        data['id'] = generate_comment_fqid(author, entry)
        data['published'] = timezone.now().isoformat()
        data.pop('author', None)

        serializer = CommentSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        comment = serializer.save(entry=entry, author=author)
        activity = create_comment_activity(author, entry, comment)
        distribute_activity(activity, actor=author)

        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        operation_summary="List all comments by a user",
        operation_description="Returns a paginated list of comments created by the specified author.",
        responses={
            200: openapi.Response(description="Comments retrieved successfully"),
            404: openapi.Response(description="Author not found"),
        }
    )
    def get(self, request, author_serial=None, comment_serial=None):
        if comment_serial:
            # Retrieve a specific comment
            comment = Comment.objects.filter(id=comment_serial).first() or Comment.objects.filter(id=comment_serial.rstrip('/') + '/').first()
            if not comment:
                return Response({'detail': 'comment not found'}, status=status.HTTP_404_NOT_FOUND)
            if author_serial and author_serial not in comment.author.id:
                return Response({'detail': 'comment not found for this author'}, status=status.HTTP_404_NOT_FOUND)
            return Response(CommentSerializer(comment).data, status=status.HTTP_200_OK)
        else:
            # Retrieve all comments by author
            author = Author.objects.filter(id__contains=author_serial).first()
            if not author:
                return Response({'detail':'Author not found'}, status=status.HTTP_404_NOT_FOUND)

            qs = Comment.objects.filter(author_id=author.id).order_by('-published')
            page_obj = paginate(request, qs)
            items = CommentSerializer(page_obj.object_list, many=True).data

            collection = {
                "type": "comments",
                "id": request.build_absolute_uri(),
                "size": qs.count(),
                "items": items,
            }
            if page_obj.has_next():
                next_page = page_obj.next_page_number()
                collection['next'] = f"{request.build_absolute_uri('?page=' + str(next_page))}"
            if page_obj.has_previous():
                prev_page = page_obj.previous_page_number()
                collection['prev'] = f"{request.build_absolute_uri('?page=' + str(prev_page))}"

            return Response(collection, status=status.HTTP_200_OK)


        