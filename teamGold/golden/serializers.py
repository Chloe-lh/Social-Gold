from rest_framework import serializers
from golden.models import Entry, Comments, Like, Follow


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
