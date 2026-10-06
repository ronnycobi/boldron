"""Customer-facing API error handling (tech-confidentiality rule).

Handled errors (validation, permission, not-found, throttling) return DRF's clean
structured 4xx JSON — these carry no framework internals and are safe. Anything
unhandled (a real server error) must NEVER leak a stack trace, exception class,
database driver, or framework detail to the customer: we log the full detail to
the internal observability system and return a single generic message.
"""
from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("platform")


def confidential_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        # DRF already produced a safe, structured client error (4xx). Pass it on.
        return response

    # Unhandled server-side exception: record everything internally, reveal nothing.
    view = context.get("view") if context else None
    logger.error("Unhandled API exception in %r", view, exc_info=exc)
    return Response(
        {"error": "Something went wrong while processing this request."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
