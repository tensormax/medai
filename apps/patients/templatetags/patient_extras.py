from datetime import date

from django import template

register = template.Library()


@register.filter
def age(birth_date, today=None):
    """Computed patient age in years. Handles a None/blank value."""
    if not birth_date:
        return ""
    today = today or date.today()
    return (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )
