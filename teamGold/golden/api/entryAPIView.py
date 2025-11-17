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
from golden.services import generate_comment_fqid, paginate

# SWAGGER
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# SERIALIZERS IMPORTS
from golden.serializers import (
    AuthorSerializer, EntrySerializer, NodeSerializer,
    FollowSerializer, LikeSerializer, CommentSerializer, EntryImageSerializer
)

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
            if obj.visibility == 'DELETED':
                return Response(status=status.HTTP_410_GONE)
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
            if entry.visibility == 'DELETED':
                return Response(status=status.HTTP_410_GONE)
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
            if entry.visibility == 'DELETED':
                return Response(status=status.HTTP_410_GONE)
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
            if entry.visibility == 'DELETED':
                return Response(status=status.HTTP_410_GONE)
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
