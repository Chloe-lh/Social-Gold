from rest_framework import generics
from rest_framework import serializers
from .models import Node


class NodeSerializer(serializers.ModelSerializer):
    class Meta: # meta data
        model = Node
        fields = '__all__'  # include all fields from model
