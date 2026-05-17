from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

# The default Django /admin/ interface is intentionally disabled.
# All management is done through the custom admin panel at /chat/admin-panel/
# which enforces role-based access controls.

urlpatterns = [
    # Redirect /admin/ to the custom admin panel instead of Django's built-in admin
    path('admin/', RedirectView.as_view(url='/chat/admin-panel/', permanent=False)),
    path('users/', include('users.urls')),
    path('chat/', include('chat.urls')),
    path('', RedirectView.as_view(url='/chat/', permanent=False)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
