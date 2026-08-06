"""Chroma vector DB client — embedded vector store for future RAG/context features."""
import chromadb
from app.config import settings

_client: chromadb.HttpClient | None = None


def get_chroma_client() -> chromadb.HttpClient:
    global _client
    if _client is None:
        _client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    return _client


def get_or_create_collection(name: str):
    return get_chroma_client().get_or_create_collection(name=name)
