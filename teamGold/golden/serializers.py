from urllib.parse import urlparse
from rest_framework import generics
from rest_framework import serializers
from django.utils import timezone
import uuid

from .services import generate_comment_fqid
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

class MinimalAuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ('id',)

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
    # Return the full nested author on reads; the view should supply an Author
    # instance when creating via `serializer.save(author=author, entry=entry)`.
    author = AuthorSerializer(read_only=True)

    id = serializers.CharField(required=False)
    published = serializers.DateTimeField(required=False)

    class Meta:
        model = Comment
        fields = '__all__'

    def create(self, validated_data):
        # DRF's `serializer.save(author=..., entry=...)` will merge those kwargs
        # into `validated_data`, so pull them out here.
        author = validated_data.pop('author', None)
        entry = validated_data.pop('entry', None)

        if author is None or entry is None:
            raise serializers.ValidationError("Both 'author' and 'entry' must be provided when creating a Comment")

        # ensure id/published
        if not validated_data.get('id'):
            validated_data['id'] = generate_comment_fqid(author, entry)
        if not validated_data.get('published'):
            validated_data['published'] = timezone.now()

        comment = Comment.objects.create(
            id=validated_data['id'],
            author=author,
            entry=entry,
            content=validated_data.get('content', ''),
            contentType=validated_data.get('contentType', Comment._meta.get_field('contentType').get_default()),
            published=validated_data.get('published'),
            reply_to=validated_data.get('reply_to', None)
        )
        return comment


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