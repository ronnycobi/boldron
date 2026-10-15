from rest_framework import serializers

from apps.developer.models import ApiKey, Webhook, WebhookDelivery


class ApiKeySerializer(serializers.ModelSerializer):
    masked = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = ApiKey
        fields = ["id", "name", "masked", "is_active", "created_at",
                  "last_used_at", "revoked_at"]
        read_only_fields = fields


class WebhookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = ["id", "url", "events", "active", "created_at"]
        read_only_fields = ["id", "created_at"]


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = ["id", "event", "status_code", "success", "error", "created_at"]
        read_only_fields = fields
