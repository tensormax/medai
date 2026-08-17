from datetime import date

from django import template

register = template.Library()


@register.filter
def age(date_of_birth):
    """Return whole years since date_of_birth (used on patient cards)."""
    if not date_of_birth:
        return ""
    today = date.today()
    years = today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )
    return years
