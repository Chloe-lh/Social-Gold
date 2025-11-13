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
    type = serializers.CharField(default="author")
    class Meta:
        model = Author
        fields = ["type","id","host","displayName","github","profileImage","web"] 

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
    author = AuthorSerializer(read_only=True)
    class Meta:
        model = Comment
        fields = [              
            'entry',  
            'author'              
            'content',          
            'content_Type',
            'published',
            "likes"
        ]

class FollowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Follow
        fields = '__all__'

class EntryImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryImage
        fields = '__all__'
        
        extra_kwargs = {
            'entry': {'read_only': True}, # By having 'entry' as an argument, we can prevent the DRF from requiring it in POST data
        }