from rest_framework import generics
from rest_framework import serializers
from .models import Node, Author, Entry, Like, Comment, Follow, EntryImage

'''
Serializers convert JSON data in order to update the Models
When a node sends data to a remote node, the API view should
use a serializer convert Model instance to JSON which is sent
in a HTTP request and vice versa
'''

class NodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Node
        fields = '__all__' 

class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = '__all__'

class EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entry
        fields = '__all__'

class LikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Like
        fields = '__all__'

class CommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', read_only=True)
    class Meta:
        model = Comment
        # only include fields that will be displayed
        fields = ['author_username', 'content', 'published']

class FollowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Follow
        fields = '__all__'

class EntryImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryImage
        fields = '__all__'

