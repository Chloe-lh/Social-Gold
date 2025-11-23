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
from bs4 import BeautifulSoup

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


class ReadingAPIView(APIView):
    """
    API view for public entries reading endpoint.
    - GET /api/reading/ returns all PUBLIC entries hosted on the node
    Matches deepskyblue spec format.
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.core.paginator import Paginator
        from golden.services import paginate
        
        # Get all PUBLIC entries, excluding deleted
        entries = Entry.objects.filter(visibility='PUBLIC').exclude(visibility='DELETED').order_by('-published')
        
        # Handle pagination
        page = request.GET.get('page', 1)
        size = request.GET.get('size', 20)
        
        try:
            page = int(page)
            size = int(size)
        except (ValueError, TypeError):
            page = 1
            size = 20
        
        # Paginate
        paginator = Paginator(entries, size)
        page_obj = paginator.get_page(page)
        
        # Serialize entries
        serializer = EntrySerializer(page_obj.object_list, many=True)
        
        # Return in deepskyblue spec format
        return Response({
            "type": "entries",
            "page_number": page,
            "size": size,
            "count": paginator.count,
            "src": serializer.data  # Changed from "items" to "src" to match spec
        }, status=status.HTTP_200_OK)


class EntryImageAPIView(APIView):
    """
    This API view handles GET, POST, PUT, and DELETE requests for an entry's images.
    - GET /api/EntryImage/<id>/ is for retrieving an entry image
    - POST /api/Entry/<entry_id>/images/ is for creating a new entry
    - DELETE /api/EntryImage/<id>/ is for deleting an entry image
    - GET /api/authors/<author_uuid>/entries/<entry_uuid>/images/ returns image list (deepskyblue spec)
    """
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id=None, author_serial=None, entry_serial=None):
        # Handle deepskyblue spec endpoint: /api/authors/<author_uuid>/entries/<entry_uuid>/images/
        if author_serial and entry_serial:
            from golden.services import fqid_to_uuid, is_local
            from django.conf import settings
            from urllib.parse import unquote
            
            # Try to find entry by UUID or FQID
            entry = None
            entry_uuid = unquote(entry_serial).rstrip('/')
            
            # If it's a UUID, construct FQID
            if '-' in entry_uuid and '/' not in entry_uuid:
                # Need author UUID too
                author_uuid = unquote(author_serial).rstrip('/')
                if '-' in author_uuid and '/' not in author_uuid:
                    entry_fqid = f"{settings.SITE_URL.rstrip('/')}/api/authors/{author_uuid}/entries/{entry_uuid}/"
                    entry = Entry.objects.filter(id=entry_fqid).first()
            
            # Try as full FQID
            if not entry:
                entry = Entry.objects.filter(id=entry_uuid).first()
            
            if not entry:
                return Response({'detail': 'Entry not found'}, status=status.HTTP_404_NOT_FOUND)
            
            # Get all images for this entry
            images = EntryImage.objects.filter(entry=entry).order_by('order', 'uploaded_at')
            
            # Format according to deepskyblue spec
            image_list = []
            
            # First, add local EntryImage objects
            for img in images:
                image_url = img.image.url
                # Make absolute URL if relative
                if image_url.startswith('/'):
                    from django.conf import settings
                    image_url = f"{settings.SITE_URL.rstrip('/')}{image_url}"
                
                image_list.append({
                    "url": image_url,
                    "uuid": None  # Spec says uuid can be null
                })
            
            # For remote entries, also extract images from HTML content if no EntryImage objects exist
            if not image_list and entry.content:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(entry.content, 'html.parser')
                img_tags = soup.find_all('img')
                for img_tag in img_tags:
                    img_src = img_tag.get('src')
                    if img_src:
                        # Make absolute if relative
                        if img_src.startswith('/'):
                            from django.conf import settings
                            img_src = f"{settings.SITE_URL.rstrip('/')}{img_src}"
                        elif not img_src.startswith('http'):
                            # Relative URL without leading slash
                            from django.conf import settings
                            img_src = f"{settings.SITE_URL.rstrip('/')}/{img_src}"
                        
                        image_list.append({
                            "url": img_src,
                            "uuid": None
                        })
            
            return Response({
                "type": "images",
                "count": len(image_list),
                "src": image_list
            }, status=status.HTTP_200_OK)
        
        # Original endpoint: GET single image by ID
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
