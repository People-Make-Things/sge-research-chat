class SgeRagError(Exception):
    """Base exception for RAG pipeline errors."""


class SourceAccessError(SgeRagError):
    """Raised when a fetcher cannot access the source site."""


class ArticleExtractionError(SgeRagError):
    """Raised when an article cannot be extracted from a page payload."""

