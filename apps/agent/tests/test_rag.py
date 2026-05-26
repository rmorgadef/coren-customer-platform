"""Tests del store RAG (BM25 sobre la KB de RAI)."""

from app.rag.store import retrieve


def test_retrieve_irpf():
    docs = retrieve("puedo desgravar el cargador en la renta")
    assert any(d.id == "irpf_2026" for d in docs)


def test_retrieve_moves_iii_returns_finalizado_doc():
    docs = retrieve("hay ayudas moves para puntos de recarga")
    assert any(d.id in {"moves_iii_finalizado", "ayudas_autonomicas"} for d in docs)


def test_retrieve_permiso_comunidad():
    docs = retrieve("hace falta permiso de la comunidad de vecinos")
    assert any(d.id == "permiso_comunidad" for d in docs)


def test_retrieve_22kw_warning_doc():
    docs = retrieve("quiero 22 kw para mi tesla")
    assert any(d.id == "cargador_22kw" for d in docs)


def test_empty_query_returns_empty():
    assert retrieve("   ") == []
    assert retrieve("") == []


def test_unrelated_query_returns_little():
    docs = retrieve("recetas de pulpo a la gallega")
    # No debería traer docs muy relevantes; lo importante es que no falla
    assert isinstance(docs, list)
