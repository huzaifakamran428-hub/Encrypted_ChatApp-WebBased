"""
Session timeout middleware — automatically expires sessions after 30 minutes
of inactivity and redirects unauthenticated users to the login page.
"""
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
import datetime

SESSION_TIMEOUT_SECONDS = getattr(settings, 'SESSION_IDLE_TIMEOUT', 1800)  # 30 minutes


class SessionIdleTimeoutMiddleware(MiddlewareMixin):
    """
    Logs the user out if they have been idle for more than SESSION_IDLE_TIMEOUT seconds.
    On each request the 'last_activity' timestamp is refreshed.
    """

    # Paths that are always allowed (login, register, OTP etc.)
    EXEMPT_PATHS = [
        '/users/login/',
        '/users/register/',
        '/users/send-otp/',
        '/users/verify-otp/',
        '/users/logout/',
        '/users/check-username/',
        '/static/',
        '/media/',
    ]

    def process_request(self, request):
        # Skip exempted paths
        path = request.path_info
        if any(path.startswith(p) for p in self.EXEMPT_PATHS):
            return None

        if not request.user.is_authenticated:
            return None

        now = timezone.now()
        last_activity_str = request.session.get('last_activity')

        if last_activity_str:
            try:
                last_activity = datetime.datetime.fromisoformat(last_activity_str)
                elapsed = (now - last_activity).total_seconds()
                if elapsed > SESSION_TIMEOUT_SECONDS:
                    logout(request)
                    login_url = settings.LOGIN_URL
                    return redirect(
                        f'{login_url}?next={request.path}&reason=timeout'
                    )
            except (ValueError, TypeError):
                pass  # malformed timestamp — reset it below

        # Update last activity on every valid request
        request.session['last_activity'] = now.isoformat()
        return None
