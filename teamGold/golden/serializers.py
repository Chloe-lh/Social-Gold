from rest_framework import generics
from rest_framework import serializers
from .models import Node, Author, Entry, Like, Comments, Follow, EntryImage

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
        model = Comments
        fields = '__all__'

class FollowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Follow
        fields = '__all__'

class EntryImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryImage
        fields = '__all__'

class InboxSerializer(serializers.Serializer):
    type = serializers.CharField()
    author = serializers.URLField(required=False)
    object = serializers.JSONField()

    def create(self, validated_data):
        type_ = validated_data["type"].lower()
        obj_data = validated_data["object"]

        if type_ == "follow":
            return Follow.objects.create(**obj_data)
        elif type_ == "Like":
            return Like.objects.create(**obj_data)
        elif type_ == "comment":
            return Comments.objects.create(**obj_data)
        elif type_ == "entry":
            return Entry.objects.create(**obj_data)
        else:
            raise serializers.ValidationError(f"Unsupported type: {type_}")
