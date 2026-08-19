from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("accounts/",  include("apps.accounts.urls")),
    path("patients/",  include("apps.patients.urls")),
    path("tasks/",     include("apps.tasks.urls")),
    path("visits/",    include("apps.visits.urls")),
    path("documents/", include("apps.documents.urls")),
    path("admin/",     admin.site.urls),
    path("", RedirectView.as_view(pattern_name="tasks:dashboard", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
