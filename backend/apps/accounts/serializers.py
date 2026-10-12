from rest_framework import serializers

from apps.accounts.models import User


class MembershipSummarySerializer(serializers.Serializer):
    """Read-only view of one organization the user belongs to."""

    id = serializers.IntegerField(source="organization.id")
    name = serializers.CharField(source="organization.name")
    slug = serializers.SlugField(source="organization.slug")
    role = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    organizations = serializers.SerializerMethodField()
    display_name = serializers.CharField(read_only=True)
    initials = serializers.CharField(read_only=True)
    avatar_url = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "display_name", "initials", "avatar_url",
            "email_verified", "language", "timezone", "date_joined", "organizations",
        ]
        read_only_fields = fields

    def get_organizations(self, obj):
        memberships = obj.memberships.select_related("organization")
        return MembershipSummarySerializer(memberships, many=True).data
