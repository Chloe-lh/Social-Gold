from rest_framework import generics
from rest_framework import serializers
import uuid
from django.utils import timezone
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

    def create(self, validated_data):
        """
        Create a Comment model instance from validated_data.
        The view may call `serializer.save(author=author, entry=entry, content=..., content_type=...)`
        so `validated_data` can include 'author' and 'entry' (model instances) and either
        'contentType' or 'content_type'. We normalize keys and create the Comment directly.
        """
        # Extract relations that the view may pass in via serializer.save(...)
        author = validated_data.pop('author', None)
        entry = validated_data.pop('entry', None)

        # Support both camelCase and snake_case keys for content type
        content = validated_data.pop('content', None)
        if content is None:
            # some callers may use 'comment' or pass content via kwargs
            content = validated_data.pop('comment', '')

        content_type = validated_data.pop('contentType', None)
        if content_type is None:
            content_type = validated_data.pop('content_type', None)
        if content_type is None:
            content_type = 'text/plain'

        # id may be provided by the view (FQID); if not, leave blank and let caller handle it
        comment_id = validated_data.pop('id', None)

        # published may be provided as a datetime or string; fall back to now
        published = validated_data.pop('published', None) or timezone.now()

        # reply_to handling: accept either an object or an id
        reply_to = validated_data.pop('reply_to', None)

        # Build and save the Comment instance
        kwargs = {
            'id': comment_id or str(uuid.uuid4()),
            'author': author,
            'entry': entry,
            'content': content or '',
            'contentType': content_type,
            'published': published,
        }
        if reply_to:
            kwargs['reply_to'] = reply_to

        # Create and return the model instance
        comment = Comment.objects.create(**kwargs)
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