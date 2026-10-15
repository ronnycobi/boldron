"""Account security services: login history + active-session tracking.

These power the Security Center (spec §9/§12/§13). No precise location is stored
— only what request headers provide (IP, user-agent). The user-agent is parsed
into a coarse browser/OS label for display, never anything more identifying.
"""
from __future__ import annotations

from django.utils import timezone

from apps.accounts.models import LoginEvent, UserSession
from apps.core.throttle import client_ip


def _ua(request) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:400]


def parse_user_agent(ua: str) -> dict:
    """Coarse browser + OS for display (no fingerprinting)."""
    u = (ua or "").lower()
    if "flutter" in u or "dart" in u:
        browser = "Mobile app"
    elif "edg/" in u:
        browser = "Edge"
    elif "firefox" in u:
        browser = "Firefox"
    elif "chrome" in u and "chromium" not in u:
        browser = "Chrome"
    elif "safari" in u:
        browser = "Safari"
    else:
        browser = "Unknown"
    if "android" in u:
        os_name = "Android"
    elif "iphone" in u or "ipad" in u or " ios" in u:
        os_name = "iOS"
    elif "mac os" in u or "macintosh" in u:
        os_name = "macOS"
    elif "windows" in u:
        os_name = "Windows"
    elif "linux" in u:
        os_name = "Linux"
    else:
        os_name = "Unknown"
    return {"browser": browser, "os": os_name}


def record_event(user, request, kind: str, *, email: str = "") -> None:
    LoginEvent.objects.create(
        user=user if (user and getattr(user, "pk", None)) else None,
        email=email or (getattr(user, "email", "") if user else ""),
        kind=kind,
        ip=client_ip(request),
        user_agent=_ua(request),
    )


def record_login(user, request) -> None:
    """Successful web login: event + upsert the UserSession for this session key."""
    record_event(user, request, LoginEvent.LOGIN_SUCCESS)
    key = request.session.session_key
    if key:
        UserSession.objects.update_or_create(
            session_key=key,
            defaults={
                "user": user,
                "ip": client_ip(request),
                "user_agent": _ua(request),
                "last_active": timezone.now(),
            },
        )


def record_failed(email: str, request) -> None:
    LoginEvent.objects.create(
        email=email, kind=LoginEvent.LOGIN_FAILED,
        ip=client_ip(request), user_agent=_ua(request),
    )


def touch(session_key: str) -> None:
    """Best-effort last-active update for a session (throttled by caller)."""
    if session_key:
        UserSession.objects.filter(session_key=session_key).update(
            last_active=timezone.now()
        )


def active_sessions(user) -> list[UserSession]:
    """UserSessions whose Django session is still live (not expired/logged out)."""
    from django.contrib.sessions.models import Session

    live = set(
        Session.objects.filter(expire_date__gte=timezone.now())
        .values_list("session_key", flat=True)
    )
    return [s for s in user.sessions.all() if s.session_key in live]


def revoke_session(user, session_key: str, request=None) -> bool:
    s = user.sessions.filter(session_key=session_key).first()
    return _revoke(user, s, request)


def revoke_session_by_id(user, session_id, request=None) -> bool:
    """Revoke by the UserSession id (so the API never takes a raw session key)."""
    s = user.sessions.filter(id=session_id).first()
    return _revoke(user, s, request)


def _revoke(user, s, request) -> bool:
    from django.contrib.sessions.models import Session

    if s is None:
        return False
    Session.objects.filter(session_key=s.session_key).delete()
    s.delete()
    if request is not None:
        record_event(user, request, LoginEvent.SESSION_REVOKED)
    return True


def security_status(user) -> dict:
    """Account security summary (real state). MFA fields are honest placeholders
    until Phase 1b implements MFA."""
    return {
        "password_set": user.has_usable_password(),
        "mfa_enabled": False,
        "mfa_available": False,
        "active_sessions": len(active_sessions(user)),
        "email_verified": user.email_verified,
    }


def session_dict(s: UserSession, *, current_key: str = "") -> dict:
    agent = parse_user_agent(s.user_agent)
    return {
        "id": s.id,
        "browser": agent["browser"],
        "os": agent["os"],
        "ip": s.ip,
        "created_at": s.created_at.isoformat(),
        "last_active": s.last_active.isoformat(),
        "current": s.session_key == current_key,
    }


def event_dict(e: LoginEvent) -> dict:
    agent = parse_user_agent(e.user_agent)
    return {
        "kind": e.kind,
        "kind_display": e.get_kind_display(),
        "browser": agent["browser"],
        "os": agent["os"],
        "ip": e.ip,
        "created_at": e.created_at.isoformat(),
    }
