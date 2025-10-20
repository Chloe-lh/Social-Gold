

from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated

from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from golden.models import Author, Entry, Comments, Like, Follow, Node, EntryImage
import uuid
from datetime import datetime

from .serializers import (
    AuthorSerializer, EntrySerializer, NodeSerializer,
    FollowSerializer, LikeSerializer, CommentSerializer, EntryImageSerializer
)

'''
Django REST Framework view that returns authors profiles data
as JSON data for other API nodes 
    - when a remote node wants to display an authors profile from our local node
    - remote node sends a GET request to our API endpoint (http:://golden.node.com/api/profile/<id>)
    - our node handles the request and serializers authors data to JSON

   some info:
   - class based API views 
        - complex endpoints
        - ei. sending profile data
   - function based API views
        - minimal logic
        - ei. sending a notification
'''
 
class GETProfileAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Author.objects.get(pk=id) 
        except Author.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(AuthorSerializer(obj).data, status=status.HTTP_200_OK)


class GETEntryAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Entry.objects.get(pk=id) 
        except Entry.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(EntrySerializer(obj).data, status=status.HTTP_200_OK)


class GETNodeAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Node.objects.get(pk=id) 
        except Node.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(NodeSerializer(obj).data, status=status.HTTP_200_OK)


class GETFollowAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Follow.objects.get(pk=id)  
        except Follow.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(FollowSerializer(obj).data, status=status.HTTP_200_OK)


class GETLikeAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Like.objects.get(pk=id)
        except Like.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(LikeSerializer(obj).data, status=status.HTTP_200_OK)


class GETCommentAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Comments.objects.get(pk=id) 
        except Comments.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(CommentSerializer(obj).data, status=status.HTTP_200_OK)


class GETEntryImageAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = EntryImage.objects.get(pk=id) 
        except EntryImage.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(EntryImageSerializer(obj).data, status=status.HTTP_200_OK)