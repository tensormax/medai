from django import template
from django.utils.html import escape, linebreaks
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="markdown")
def markdown_filter(value):
    """
    Render message/insight content. Uses the `markdown` package when
    available; otherwise falls back to escaped text with line breaks.
    """
    if not value:
        return ""
    try:
        import markdown as md

        return mark_safe(md.markdown(value))
    except ImportError:
        return mark_safe(linebreaks(escape(value)))
