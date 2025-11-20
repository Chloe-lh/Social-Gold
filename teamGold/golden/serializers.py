from urllib.parse import urlparse
from rest_framework import generics
from rest_framework import serializers
from django.utils import timezone
import uuid

from .services import generate_comment_fqid
from .models import Node, Author, Entry, Like, Comment, Follow, EntryImage, Inbox

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

    ''' this helps with shape validation and nesting'''
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

        like = Like.objects.create(
            id=validated_data['id'],
            author=author,
            entry=entry,
            published=validated_data.get('published'),
        )
        return like

class CommentSerializer(serializers.ModelSerializer):
    # Return the full nested author on reads; the view should supply an Author
    # instance when creating via `serializer.save(author=author, entry=entry)`.
    author = AuthorSerializer(read_only=True)

    id = serializers.CharField(required=False)
    published = serializers.DateTimeField(required=False)

    class Meta:
        model = Comment
        fields = '__all__'

    ''' this helps with shape validation and nesting'''
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
class AuthorInboxSerializer(serializers.Serializer):
    class Meta:
        model = Author
        fields = [
            'id',
            'host',
            'web',
            'github',
            'username'
        ]
    type = serializers.CharField(default="author")
    
    profileImage = serializers.URLField(required=False, allow_blank=True)

    def validate_type(self, value):
        if value.lower() != "author":
            raise serializers.ValidationError("type must be 'author'")
        return value

class FollowRequestInboxSerializer(serializers.Serializer):
    type = serializers.CharField()
    actor = AuthorInboxSerializer()
    object = AuthorInboxSerializer()
    class Meta:
        model = Follow
        fields = [
            'summary'
        ]

    def validate_type(self, value):
        if value.lower() != "follow":
            raise serializers.ValidationError("type must be 'follow'")
        return value
    
class CommentInboxSerializaer(serializers.Serializer):
    type = serializers.CharField()
    author = AuthorInboxSerializer()

    class Meta:
        model = Comment
        fields = [
        'contentType',
        'published',
        'id',
        'entry'
        ]
    comment = serializers.CharField(max_length=200, allow_blank=True)
    def validate_type(self, value):
        if value.lower() != "comment":
            raise serializers.ValidationError("type must be 'comment'")
        return value
    
class LikeInboxSerializer(serializers.Serializer):
    type = serializers.CharField()

    author = AuthorInboxSerializer()
    class Meta:
        model = Like
        fields = [
            'published',
            'id',
            'object'
        ]
    def validate_type(self, value):
        if value.lower() != "like":
            raise serializers.ValidationError("type must be 'like'")
        return value

'''
validation for specific entry items
'''
class CommentsInfoSerializer(serializers.Serializer):
    type = serializers.CharField(default="comments")
    id = serializers.URLField()
    web = serializers.URLField(required=False)
    page_number = serializers.IntegerField(required=False)
    size = serializers.IntegerField(required=False)
    count = serializers.IntegerField(required=False)
    src = serializers.ListField(child=serializers.DictField(), required=False)

    
class LikesInfoSerializer(serializers.Serializer):
    type = serializers.CharField(default="likes")
    id = serializers.URLField()
    web = serializers.URLField(required=False)
    page_number = serializers.IntegerField(required=False)
    size = serializers.IntegerField(required=False)
    count = serializers.IntegerField(required=False)
    src = serializers.ListField(child=serializers.DictField(), required=False)

class EntryInboxSerializer(serializers.Serializer):
    type = serializers.CharField()
    class Meta:
        model = Entry
        fields = [
            'title',
            'id',
            'web',
            'description',
            'contentType',
            'content',
            'published',
            'visibility'

        ]
    comments = CommentsInfoSerializer(required = False)
    likes = LikesInfoSerializer(required = False)
    author = AuthorInboxSerializer()


    def validate_type(self, value):
        if value.lower() not in ["entry", "create", "post"]:
            raise serializers.ValidationError("type must be entry/create/post")
        return value

class InboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inbox
        fields = ['id', 'author', 'data', 'received_at']
        read_only_fields = ['id', 'received_at']