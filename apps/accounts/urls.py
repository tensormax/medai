from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/",  views.SignUpView.as_view(),       name="account_signup"),
    path("login/",   views.CustomLoginView.as_view(),   name="account_login"),
    path("logout/",  views.CustomLogoutView.as_view(),  name="account_logout"),
]
