import html

import markdown as md
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def markdown(value):
    """
    Render message text as HTML (headers, bold, bullet lists) for the
    visual structure of AI notes. Input is HTML-escaped first so any
    stray markup in model content stays inert. Template-level formatting
    only — no new fields, no stored HTML.
    """
    if not value:
        return ""
    escaped = html.escape(str(value))
    return mark_safe(md.markdown(escaped, extensions=["extra"]))
