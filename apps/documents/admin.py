from django.contrib import admin

from .models import Document, DocumentAnalysis, DocumentChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "patient", "kind", "doc_type", "de_identified", "uploaded_at"]
    list_filter = ["kind", "doc_type", "de_identified"]


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ["document", "chunk_index", "embedding_id", "created_at"]


@admin.register(DocumentAnalysis)
class DocumentAnalysisAdmin(admin.ModelAdmin):
    list_display = ["document", "analysis_type", "created_at"]
    list_filter = ["analysis_type"]
