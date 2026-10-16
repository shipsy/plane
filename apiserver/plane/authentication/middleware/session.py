import time
from importlib import import_module

from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import http_date


class SessionMiddleware(MiddlewareMixin):
    def __init__(self, get_response):
        super().__init__(get_response)
        engine = import_module(settings.SESSION_ENGINE)
        self.SessionStore = engine.SessionStore

    def process_request(self, request):
        if "instances" in request.path:
            session_key = request.COOKIES.get(
                settings.ADMIN_SESSION_COOKIE_NAME
            )
        else:
            session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        request.session = self.SessionStore(session_key)

    def refresh_session_expiry(self, request):
        """
        Keep active users signed in: renew the expiry of a logged in session
        once half of its lifetime has passed. Idle sessions still expire.
        """
        session = getattr(request, "session", None)
        if session is None or "instances" in request.path:
            return
        if not session.get("_auth_user_id"):
            return
        now = int(time.time())
        if now - session.get("_expiry_refreshed_at", 0) >= settings.SESSION_COOKIE_AGE // 2:
            session["_expiry_refreshed_at"] = now

    def process_response(self, request, response):
        """
        If request.session was modified, or if the configuration is to save the
        session every time, save the changes and set a session cookie or delete
        the session cookie if the session has been emptied.
        """
        self.refresh_session_expiry(request)
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            return response
        # First check if we need to delete this cookie.
        # The session should be deleted only if the session is entirely empty.
        is_admin_path = "instances" in request.path
        cookie_name = (
            settings.ADMIN_SESSION_COOKIE_NAME
            if is_admin_path
            else settings.SESSION_COOKIE_NAME
        )

        if cookie_name in request.COOKIES and empty:
            response.delete_cookie(
                cookie_name,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )
            patch_vary_headers(response, ("Cookie",))
        else:
            if accessed:
                patch_vary_headers(response, ("Cookie",))
            if (modified or settings.SESSION_SAVE_EVERY_REQUEST) and not empty:
                if request.session.get_expire_at_browser_close():
                    max_age = None
                    expires = None
                else:
                    # Use different max_age based on whether it's an admin cookie
                    if is_admin_path:
                        max_age = settings.ADMIN_SESSION_COOKIE_AGE
                    else:
                        max_age = request.session.get_expiry_age()

                    expires_time = time.time() + max_age
                    expires = http_date(expires_time)

                # Save the session data and refresh the client cookie.
                if response.status_code < 500:
                    try:
                        request.session.save()
                    except UpdateError:
                        raise SessionInterrupted(
                            "The request's session was deleted before the "
                            "request completed. The user may have logged "
                            "out in a concurrent request, for example."
                        )
                    response.set_cookie(
                        cookie_name,
                        request.session.session_key,
                        max_age=max_age,
                        expires=expires,
                        domain=settings.SESSION_COOKIE_DOMAIN,
                        path=settings.SESSION_COOKIE_PATH,
                        secure=settings.SESSION_COOKIE_SECURE or None,
                        httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                        samesite=settings.SESSION_COOKIE_SAMESITE,
                    )
        return response
