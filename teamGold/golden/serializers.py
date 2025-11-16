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
        # match serializer fields to actual Author model fields
        fields = ["type", "id", "host", "name", "github", "profileImage", "web"]

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
    # Accept author and entry as their FQID strings (slug fields) so incoming
    # POSTs can provide the URL identifier. This maps the provided id to the
    # corresponding Author/Entry instances.
    author = serializers.SlugRelatedField(slug_field='id', queryset=Author.objects.all())
    entry = serializers.SlugRelatedField(slug_field='id', queryset=Entry.objects.all())

    class Meta:
        model = Comment
        fields = [
            'id',
            'type',
            'author',
            'entry',
            'content',
            'contentType',
            'published',
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