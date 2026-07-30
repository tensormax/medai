from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from .forms import DoctorProfileForm, DoctorRegistrationForm


def register(request):
    if request.method == "POST":
        form = DoctorRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("accounts:login")
    else:
        form = DoctorRegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    doctor = request.user.doctor_profile
    if request.method == "POST":
        form = DoctorProfileForm(request.POST, instance=doctor)
        if form.is_valid():
            form.save()
            return redirect("accounts:profile")
    else:
        form = DoctorProfileForm(instance=doctor)
    return render(request, "accounts/profile.html", {"form": form, "doctor": doctor})


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"


class CustomLogoutView(LogoutView):
    next_page = "accounts:login"
