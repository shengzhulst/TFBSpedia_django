# home/serializers.py
from rest_framework import serializers

class TFBSSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    chromosome = serializers.CharField(source='seqnames', read_only=True)
    start = serializers.IntegerField(read_only=True)
    end = serializers.IntegerField(read_only=True)
    tf_name = serializers.CharField(read_only=True, required=False)
    score = serializers.FloatField(read_only=True, required=False)