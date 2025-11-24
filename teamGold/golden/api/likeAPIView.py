
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# DJANGO IMPORTS
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.paginator import Paginator

# PYTHON IMPORTS
from urllib.parse import unquote, urlparse
import requests
import json

# LOCAL IMPORTS
from golden.models import Author, Entry, Comment, Like
from golden.services import generate_like_fqid, paginate
from golden.distributor import distribute_activity
from golden.activities import create_like_activity

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# SERIALIZERS IMPORTS
from golden.serializers import LikeSerializer
class LikeAPIView(APIView):
    """
    API view to handle Likes for Entries and Comments.
    Supports:
    - GET /api/authors/{AUTHOR_SERIAL}/entries/{ENTRY_SERIAL}/likes
    - GET /api/authors/{AUTHOR_SERIAL}/entries/{ENTRY_SERIAL}/comments/{COMMENT_FQID}/likes
    - GET /api/entries/{ENTRY_FQID}/likes
    - POST /api/entries/{ENTRY_FQID}/like
    - POST /api/comments/{COMMENT_FQID}/like
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_summary='Get all likes for an entry or comment',
        operation_description=(
            "Returns a paginated list of Like objects for a given entry or comment. "
            "Each like includes nested author information. "
            "Supports the following URL patterns:\n"
            "- /api/authors/{AUTHOR_SERIAL}/entries/{ENTRY_SERIAL}/likes\n"
            "- /api/authors/{AUTHOR_SERIAL}/entries/{ENTRY_SERIAL}/comments/{COMMENT_FQID}/likes\n"
            "- /api/entries/{ENTRY_FQID}/likes"
        ),
        responses={
            200: openapi.Response(
                description="Likes found",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "type": openapi.Schema(type=openapi.TYPE_STRING, example="likes"),
                        "id": openapi.Schema(type=openapi.TYPE_STRING, example="http://service/api/authors/123/entries/456/likes"),
                        "size": openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
                        "items": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT)),
                        "next": openapi.Schema(type=openapi.TYPE_STRING, example="http://service/api/authors/123/entries/456/likes?page=2"),
                        "prev": openapi.Schema(type=openapi.TYPE_STRING, example="http://service/api/authors/123/entries/456/likes?page=1")
                    }
                )
            ),
            404: openapi.Response(description="Entry or comment not found"),
            400: openapi.Response(description="Bad request"),
        }
    )
    def get(self, request, author_serial=None, entry_serial=None, comment_fqid=None, *args, **kwargs):
        if not entry_serial:
            return Response({'detail': 'entry id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            entry = Entry.objects.get(id__contains=entry_serial)
        except Entry.DoesNotExist:
            return Response({'detail': 'entry not found'}, status=status.HTTP_404_NOT_FOUND)

        if author_serial and author_serial not in entry.author.id:
            return Response({'detail': 'entry not found by specified author'}, status=status.HTTP_404_NOT_FOUND)

        # Determine the target: entry or comment
        target_fqid = entry.id
        if comment_fqid:
            try:
                comment = Comment.objects.get(id__contains=comment_fqid)
            except Comment.DoesNotExist:
                return Response({'detail': 'comment not found'}, status=status.HTTP_404_NOT_FOUND)
            if comment.entry.id != entry.id:
                return Response({'detail': 'comment does not belong to the specified entry'}, status=status.HTTP_404_NOT_FOUND)
            target_fqid = comment.id

        # Paginate likes
        qs = Like.objects.filter(object=target_fqid).order_by('-published')
        page_obj = paginate(request, qs)
        items = LikeSerializer(page_obj.object_list, many=True).data

        collection = {
            "type": "likes",
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
        operation_summary="Create a like for an entry or comment",
        operation_description=(
            "User likes an entry or comment. If local, delivers to followers. "
            "URL patterns supported:\n"
            "- /api/entries/{ENTRY_FQID}/like\n"
            "- /api/comments/{COMMENT_FQID}/like"
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            description="JSON body can be empty; server assigns author automatically"
        ),
        responses={
            201: openapi.Response(description="Like created"),
            200: openapi.Response(description="Like already exists (idempotent)"),
            404: openapi.Response(description="Entry, Comment, or Author not found"),
            400: openapi.Response(description="Bad request")
        }
    )
    def post(self, request, object_id):
        if not request.content_type or 'application/json' not in request.content_type:
            return Response({'detail': 'Content-Type must be application/json'}, status=status.HTTP_400_BAD_REQUEST)

        object_id = unquote(object_id).rstrip("/")
        like_author = get_object_or_404(Author, id=request.user.id)

        # Resolve object (Comment preferred over Entry)
        liked_object = Comment.objects.filter(id=object_id).first() or Comment.objects.filter(id__endswith=object_id).first()
        if not liked_object:
            liked_object = Entry.objects.filter(id=object_id).first() or Entry.objects.filter(id__endswith=object_id).first()
        if not liked_object:
            return Response({'detail': 'Object not found'}, status=status.HTTP_404_NOT_FOUND)

        # Create like (idempotent)
        like_id = generate_like_fqid(like_author)
        published = timezone.now()
        existing = Like.objects.filter(id=like_id).first()
        if existing:
            return Response(LikeSerializer(existing).data, status=status.HTTP_200_OK)

        like = Like.objects.create(
            id=like_id,
            author=like_author,
            object=liked_object.id,
            published=published,
        )

        # Update likes M2M field
        try:
            liked_object.likes.add(like_author)
            liked_object.save(update_fields=['likes'])
        except Exception:
            pass

        activity = create_like_activity(like_author, liked_object.id)
        distribute_activity(activity, actor=like_author)

        return Response(LikeSerializer(like).data, status=status.HTTP_201_CREATED)


class LikedAPIView(APIView):
    """
    API view to get all likes by an author or a single like object.
    - GET /api/authors/{AUTHOR_SERIAL}/liked -> list of likes by author
    - GET /api/authors/{AUTHOR_SERIAL}/liked/{LIKE_SERIAL} -> single like by author
    - GET /api/liked/{LIKE_FQID} -> single like by FQID
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get all likes by an author",
        operation_description="Returns a paginated list of likes by the specified author. Supports query params ?page=<number>&size=<number>.",
        responses={
            200: openapi.Response(
                description="Likes found",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "type": openapi.Schema(type=openapi.TYPE_STRING, example="likes"),
                        "id": openapi.Schema(type=openapi.TYPE_STRING, example="http://service/api/authors/123/liked"),
                        "size": openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
                        "items": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_OBJECT)
                        ),
                        "next": openapi.Schema(type=openapi.TYPE_STRING, example="http://service/api/authors/123/liked?page=2"),
                        "prev": openapi.Schema(type=openapi.TYPE_STRING, example="http://service/api/authors/123/liked?page=1")
                    }
                )
            ),
            404: openapi.Response(description="Author not found")
        }
    )
    def get(self, request, author_serial=None, like_serial=None):
        # GET single like by LIKE_SERIAL if provided
        if like_serial:
            like = Like.objects.filter(id__contains=like_serial).first()
            if not like:
                return Response({'detail': 'Like not found'}, status=status.HTTP_404_NOT_FOUND)
            # ensure author matches if author_serial provided
            if author_serial and author_serial not in like.author.id:
                return Response({'detail': 'Like not found for this author'}, status=status.HTTP_404_NOT_FOUND)
            return Response(LikeSerializer(like).data, status=status.HTTP_200_OK)

        # Otherwise list all likes by author
        if not author_serial:
            return Response({'detail': 'author required'}, status=status.HTTP_400_BAD_REQUEST)

        author = Author.objects.filter(id__contains=author_serial).first()
        if not author:
            return Response({'detail': 'Author not found'}, status=status.HTTP_404_NOT_FOUND)

        qs = Like.objects.filter(author=author).order_by('-published')
        page_obj = paginate(request, qs)
        items = LikeSerializer(page_obj.object_list, many=True).data

        collection = {
            "type": "likes",
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



 
