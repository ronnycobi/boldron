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
            "job_title", "pronouns", "bio", "font_scale", "reduce_motion", "theme",
        ]
        read_only_fields = fields

    def get_organizations(self, obj):
        memberships = obj.memberships.select_related("organization")
        return MembershipSummarySerializer(memberships, many=True).data


class AccountUpdateSerializer(serializers.ModelSerializer):
    """Fields a user may edit on their own account."""

    class Meta:
        model = User
        fields = [
            "full_name", "email", "language", "timezone",
            "job_title", "pronouns", "bio", "font_scale", "reduce_motion", "theme",
        ]

    def validate_email(self, value):
        email = User.objects.normalize_email(value)
        if not email:
            raise serializers.ValidationError("Email can't be blank.")
        qs = User.objects.filter(email__iexact=email)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "That email is already in use by another account."
            )
        return email
