from django.contrib import admin

from .models import Visit, VisitMessage


class VisitMessageInline(admin.TabularInline):
    model = VisitMessage
    extra = 0


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ["patient", "doctor", "started_at", "status"]
    inlines = [VisitMessageInline]


@admin.register(VisitMessage)
class VisitMessageAdmin(admin.ModelAdmin):
    list_display = ["visit", "role", "content", "created_at"]
