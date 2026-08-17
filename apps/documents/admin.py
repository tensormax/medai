from django.contrib import admin

from .models import Document, DocumentAnalysis, DocumentChunk


class DocumentChunkInline(admin.TabularInline):
    model = DocumentChunk
    extra = 0
    readonly_fields = ["chunk_index", "embedding_id", "chunk_text", "created_at"]
    can_delete = False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "patient", "kind", "doc_type", "uploaded_at"]
    list_filter = ["kind", "doc_type"]
    search_fields = ["title", "patient__full_name", "patient__mrn"]
    inlines = [DocumentChunkInline]


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ["id", "document", "chunk_index", "embedding_id", "created_at"]
    search_fields = ["chunk_text"]


@admin.register(DocumentAnalysis)
class DocumentAnalysisAdmin(admin.ModelAdmin):
    list_display = ["id", "document", "analysis_type", "created_at"]
    list_filter = ["analysis_type"]
