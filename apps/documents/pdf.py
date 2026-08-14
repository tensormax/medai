"""
PDF rendering. WeasyPrint is imported lazily: its native GTK/Pango/Cairo
dependencies may not be present on every machine, and we never want an
import error at Django startup. Callers get a clear exception instead.
"""


class PDFRenderingError(Exception):
    """Raised when WeasyPrint or its native libraries are unavailable."""


def render_html_to_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise PDFRenderingError(
            "WeasyPrint is not installed (pip install weasyprint)."
        ) from exc
    try:
        return HTML(string=html).write_pdf()
    except Exception as exc:
        raise PDFRenderingError(
            "PDF rendering failed. On Windows, WeasyPrint needs the GTK "
            "runtime (gobject/pango/cairo). Original error: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
