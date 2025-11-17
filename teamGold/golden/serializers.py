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
    class Meta:
        model = Comment
        fields = '__all__'

""" 
This comment section shows an alternative, more detailed CommentSerializer
that includes custom representations. 

class CommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', read_only=True)

    class Meta:
        model = Comment
        fields = [
            'id',                 
            'author_username',   
            'entry',              
            'content',          
            'contentType',
            'published'
        ]
"""    

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
        ]
    type = serializers.CharField(default="author")
    displayName = serializers.CharField(required=True)
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
        if value.lower() != "entry":
            raise serializers.ValidationError("type must be 'entry'")
        return value