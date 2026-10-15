from rest_framework import serializers

from apps.organizations.models import Invitation, Membership, Organization, Role


class OrgUserSerializer(serializers.Serializer):
    """Minimal public view of a user inside an organization."""

    id = serializers.IntegerField()
    email = serializers.EmailField()
    display_name = serializers.CharField()
    initials = serializers.CharField()
    avatar_url = serializers.CharField()


class OrganizationSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    my_permissions = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id", "name", "slug", "description", "role", "member_count",
            "can_manage", "my_permissions", "created_at",
        ]
        read_only_fields = fields

    def _my_membership(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user:
            return None
        return obj.memberships.filter(user=user).first()

    def get_role(self, obj):
        m = self._my_membership(obj)
        return m.role if m else None

    def get_member_count(self, obj):
        return obj.memberships.count()

    def get_can_manage(self, obj):
        m = self._my_membership(obj)
        return bool(m and m.role in {Role.OWNER, Role.ADMIN})

    def get_my_permissions(self, obj):
        from apps.organizations.permissions import permissions_for_role
        m = self._my_membership(obj)
        return sorted(permissions_for_role(m.role)) if m else []


class MembershipSerializer(serializers.ModelSerializer):
    user = OrgUserSerializer()

    class Meta:
        model = Membership
        fields = ["role", "created_at", "user"]
        read_only_fields = fields


class InvitationSerializer(serializers.ModelSerializer):
    is_pending = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "status", "is_pending", "created_at", "expires_at"]
        read_only_fields = fields
