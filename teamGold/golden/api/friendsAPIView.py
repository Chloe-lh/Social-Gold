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

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# SERIALIZERS IMPORTS
from golden.serializers import NodeSerializer, AuthorSerializer


class AuthorFriendsView(APIView):
    """
    This API view handles GET requests to retrieve an author's friends (mutual followers).
    - GET /api/Author/<author_id>/friends/ will then retrieve a list of friends
    Works for both local and remote authors.
    """
    def get(self, request, author_id):
        author = get_object_or_404(Author, id=author_id)

        # Use get_friends from distributor which works with Follow objects for both local and remote
        from golden.distributor import get_friends
        friends_qs = get_friends(author)

        serializer = AuthorSerializer(friends_qs, many=True)
        return Response(serializer.data)
    
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
