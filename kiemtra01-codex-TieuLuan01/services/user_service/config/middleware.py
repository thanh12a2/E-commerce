import time

from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date


class ScopedSessionMiddleware(SessionMiddleware):
    """Use separate browser sessions for customer and staff UI routes."""

    def _cookie_name_and_path(self, request):
        path = request.path_info or request.path
        if path.startswith("/staff/"):
            return settings.STAFF_SESSION_COOKIE_NAME, "/staff/"
        if path.startswith("/customer/"):
            return settings.CUSTOMER_SESSION_COOKIE_NAME, "/customer/"
        return settings.SESSION_COOKIE_NAME, settings.SESSION_COOKIE_PATH

    def process_request(self, request):
        cookie_name, cookie_path = self._cookie_name_and_path(request)
        request.scoped_session_cookie_name = cookie_name
        request.scoped_session_cookie_path = cookie_path
        session_key = request.COOKIES.get(cookie_name)
        if session_key is None and cookie_name != settings.SESSION_COOKIE_NAME:
            session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        request.session = self.SessionStore(session_key)

    def process_response(self, request, response):
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            return response

        cookie_name = getattr(request, "scoped_session_cookie_name", settings.SESSION_COOKIE_NAME)
        cookie_path = getattr(request, "scoped_session_cookie_path", settings.SESSION_COOKIE_PATH)

        if cookie_name in request.COOKIES and empty:
            response.delete_cookie(
                cookie_name,
                path=cookie_path,
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
                    max_age = request.session.get_expiry_age()
                    expires_time = None if max_age is None else max_age + time.time()
                    expires = None if expires_time is None else http_date(expires_time)

                if response.status_code < 500:
                    try:
                        request.session.save()
                    except UpdateError:
                        raise SessionInterrupted(
                            "The request's session was deleted before the request completed."
                        )
                    response.set_cookie(
                        cookie_name,
                        request.session.session_key,
                        max_age=max_age,
                        expires=expires,
                        domain=settings.SESSION_COOKIE_DOMAIN,
                        path=cookie_path,
                        secure=settings.SESSION_COOKIE_SECURE or None,
                        httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                        samesite=settings.SESSION_COOKIE_SAMESITE,
                    )
        return response
