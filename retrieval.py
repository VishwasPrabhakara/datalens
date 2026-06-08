"""
DataLens — Hybrid Retrieval over schema.

Identical pattern to PaperLens:
  - FAISS for semantic matching (catches "songs by X" → Track table)
  - BM25 for exact-term matching (catches "find the InvoiceLine row")
  - Reciprocal Rank Fusion merges the two ranked lists.

Returns the top-K most relevant table Documents for a given question.
"""
from __future__ import annotations

from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EMBED_MODEL = "models/gemini-embedding-001"
TOP_K_RETRIEVE = 5  # smaller than PaperLens — schemas have far fewer "chunks"


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def _doc_key(doc: Document) -> str:
    """Identity key for a table Document — uses table_name for uniqueness."""
    return f"{doc.metadata.get('db_path')}::{doc.metadata.get('table_name')}"


def _rrf_merge(
    list_a: list[Document], list_b: list[Document], k: int, c: int = 60
) -> list[Document]:
    """Score-free fusion of two ranked lists. c=60 is the paper's constant."""
    scores: dict[str, float] = {}
    by_key: dict[str, Document] = {}

    for ranked_list in (list_a, list_b):
        for rank, doc in enumerate(ranked_list):
            key = _doc_key(doc)
            scores[key] = scores.get(key, 0.0) + 1.0 / (c + rank + 1)
            by_key[key] = doc

    fused_keys = sorted(scores, key=scores.get, reverse=True)
    return [by_key[key] for key in fused_keys[:k]]


# ---------------------------------------------------------------------------
# Hybrid retriever
# ---------------------------------------------------------------------------


class SchemaRetriever:
    """Hybrid retriever over table Documents.

    Built once per database. Reused for every question against that DB.
    """

    def __init__(self, documents: list[Document], api_key: str, k: int = TOP_K_RETRIEVE):
        if not documents:
            raise RuntimeError("No documents provided to SchemaRetriever.")
        embeddings = GoogleGenerativeAIEmbeddings(
            model=EMBED_MODEL,
            google_api_key=api_key,
        )
        self.vector_store = FAISS.from_documents(documents, embeddings)
        self.bm25 = BM25Retriever.from_documents(documents)
        self.bm25.k = k
        self.k = k

    def retrieve(self, question: str) -> list[Document]:
        """Return top-K relevant tables for the question."""
        semantic = self.vector_store.similarity_search(question, k=self.k)
        keyword = self.bm25.invoke(question)
        return _rrf_merge(semantic, keyword, k=self.k)