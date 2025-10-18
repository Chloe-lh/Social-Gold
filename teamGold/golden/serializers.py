from rest_framework import generics
from rest_framework import serializers
from .models import Node, Author, Entry, Like, Comment, Follow

'''

'''

class NodeSerializer(serializers.ModelSerializer):
    class Meta: # meta data
        model = Node
        fields = '__all__'  # include all fields from model

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
    class Meta:
        model = Comment
        fields = '__all__'

class FollowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Follow
        fields = '__all__'
