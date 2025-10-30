

from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated

from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from golden.models import Author, Entry, Comment, Like, Follow, Node, EntryImage
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
 
class ProfileAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Author.objects.get(pk=id) 
        except Author.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(AuthorSerializer(obj).data, status=status.HTTP_200_OK)
    
    def post(self, request, id):
        pass


class EntryAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Entry.objects.get(pk=id) 
        except Entry.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(EntrySerializer(obj).data, status=status.HTTP_200_OK)
    
    def post(self, request, id):
        pass


class NodeAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Node.objects.get(pk=id) 
        except Node.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(NodeSerializer(obj).data, status=status.HTTP_200_OK)
    
    def post(self,request,id):
        pass


class FollowAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Follow.objects.get(pk=id)  
        except Follow.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(FollowSerializer(obj).data, status=status.HTTP_200_OK)
    
    def post(self, request, id):
        pass 


class LikeAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = Like.objects.get(pk=id)
        except Like.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(LikeSerializer(obj).data, status=status.HTTP_200_OK)
    
    def post(self, request, id):
        pass



class CommentAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    # get ALL comments for a given entry
    def get(self, request, entry_id):
        comments = Comment.objects.filter(entry_id=entry_id).order_by('-published')
        serializer = CommentSerializer(comments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # add new comment to a given entry
    def post(self, request, entry_id):
        try:
            entry = Entry.objects.get(pk=entry_id)
        except Entry.DoesNotExist:
            return Response({'error': 'Entry not found'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = CommentSerializer(data=request.data)
        # ensures only safe data is saved
        # checks all required fields
        if serializer.is_valid():
            # add comment to comments
            serializer.save(entry=entry, author=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EntryImageAPIView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            obj = EntryImage.objects.get(pk=id) 
        except EntryImage.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(EntryImageSerializer(obj).data, status=status.HTTP_200_OK)
    
    def post(self, request, id):
        pass