from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("accounts/",  include("apps.accounts.urls")),
    path("patients/",  include("apps.patients.urls")),
    path("admin/",     admin.site.urls),
]
