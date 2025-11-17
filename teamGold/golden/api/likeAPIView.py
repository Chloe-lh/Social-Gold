
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
from golden.services import generate_comment_fqid, paginate

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# SERIALIZERS IMPORTS
from golden.serializers import (
    AuthorSerializer, EntrySerializer, NodeSerializer,
    FollowSerializer, LikeSerializer, CommentSerializer, EntryImageSerializer
)

class LikeAPIView(APIView):
    """
    This API view handles GET requests to retrieve like data by ID.
    - GET /api/like/<id>/ will then retrieve like data
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

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

        collection = {
            "type": "likes",
            "id": collection_id,
            "web": collection_id.replace('/api/', '/'),
            "page_number": page_number,
            "size": page_size,
            "count": paginator.count,
            "src": serialized,
        }

        # Return the collection
        return Response(collection, status=status.HTTP_200_OK)
    
    def post(self, request, entry_id):
        pass


class CommentLikeAPIView(APIView):
    """
    GET/POST a paginated list of likes for a Comment object (by Comment FQID or suffix).

    GET returns an ActivityPub-like collection. POST creates a Like.
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    
    # #Get a single comment
    # def get(self, request, comment_id):
    #     # comment_id may be a full FQID or a UUID suffix
    #     comment_id = unquote(comment_id).rstrip('/')

    #     likes_qs = Like.objects.filter(object=comment_id).order_by('-published')

    #     # Pagination parameters
    #     try:
    #         page_size = int(request.query_params.get('size', 5))
    #     except Exception:
    #         page_size = 5
    #     try:
    #         page_number = int(request.query_params.get('page', 1))
    #     except Exception:
    #         page_number = 1

    #     paginator = Paginator(likes_qs, page_size)
    #     page_obj = paginate(requst, likes_qs)

    #     serialized = LikeSerializer(page_obj.object_list, many=True).data

    #     host = request.build_absolute_uri('/').rstrip('/')
    #     collection_id = f"{host}/api/Comment/{comment_id}/likes/"

    #     collection = {
    #         "type": "likes",
    #         "id": collection_id,
    #         "web": collection_id.replace('/api/', '/'),
    #         "page_number": page_number,
    #         "size": page_size,
    #         "count": paginator.count,
    #         "src": serialized,
    #     }

    #     return Response(collection, status=status.HTTP_200_OK)

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
