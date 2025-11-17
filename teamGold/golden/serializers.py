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
        fields = '__all__'

class EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entry
        fields = '__all__'

class LikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Like
        fields = '__all__'

'''
added ability to have a nested Author object
'''
class CommentSerializer(serializers.ModelSerializer):
    # Return a nested author object on reads, but treat author as read-only
    # for serializer input. The view will resolve/create the Author instance
    # and pass it to `serializer.save(author=author)` during POST handling.
    author = AuthorSerializer(read_only=True)
    # Allow `id` and `published` to be omitted from incoming payloads
    id = serializers.CharField(required=False)
    published = serializers.DateTimeField(required=False)
    class Meta:
        model = Comment
        # Explicit fields matching Comment model
        fields = [
            'id',
            'type',
            'author',
            'entry',
            'content',
            'contentType',
            'published',
            'reply_to',
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