import django
from django.conf import settings
from django.utils.text import slugify
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness probe. Public by design so load balancers can reach it.

    Returns the running Django version so a deploy can be verified end to end.
    This is the one endpoint that proves the repository foundation runs.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                # Brand-neutral service id, derived from configuration.
                "service": slugify(settings.APP_NAME) or "app",
                "status": "ok",
                "django": django.get_version(),
            }
        )
