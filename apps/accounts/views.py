from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic.edit import CreateView
from django.urls import reverse_lazy


class SignUpView(CreateView):
    """New-user registration using Django's built-in UserCreationForm."""
    form_class = UserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("accounts:account_login")


class CustomLoginView(LoginView):
    """Login using Django's built-in AuthenticationForm."""
    form_class = AuthenticationForm
    template_name = "accounts/login.html"
    # On success, LOGIN_REDIRECT_URL from settings.py is used.


class CustomLogoutView(LogoutView):
    """Log out and redirect to the login page."""
    next_page = reverse_lazy("accounts:account_login")
