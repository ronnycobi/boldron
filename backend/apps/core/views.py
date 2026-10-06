from django.conf import settings
from django.utils.text import slugify
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness probe. Public by design so load balancers can reach it.

    Intentionally minimal: a brand-neutral service id and an "ok" status, with no
    implementation details. The platform's framework and its version are internal
    and must never be exposed on a public endpoint (tech-confidentiality rule).
    """

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                # Brand-neutral service id, derived from configuration.
                "service": slugify(settings.APP_NAME) or "app",
                "status": "ok",
            }
        )
