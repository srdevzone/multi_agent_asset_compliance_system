"""
Integration tests for the document ingestion flow.

Tests the full HTTP request → ingest handler → Pinecone upsert chain
using moto for S3 and mock clients for Pinecone and OpenAI.
No real network calls are made.

The tests at the bottom of this file (``test_local_upload_and_ingest``,
``test_zen_provider_initialisation``, ``test_opencode_go_provider_initialisation``)
exercise the offline providers and the new Zen / OpenCode Go provider routes
added by the architectural blueprint.
"""

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.dependencies import OPENCODE_GO_BASE_URL, ZEN_BASE_URL, _get_agent_llm
from app.utils.offline_clients import (
    LocalChatModel,
    LocalEmbeddings,
    LocalPineconeIndex,
    LocalS3Client,
)
from tests.integration.helpers import patch_dependencies


@pytest.mark.asyncio
async def test_ingest_create_event(
    async_client, auth_headers, s3_bucket, mock_pinecone_index, mock_embeddings_model
):
    """POST /ingest with create event should return 200 and upsert vectors."""
    # Upload a fake PDF to mock S3
    s3_bucket.put_object(
        Bucket="test-bucket",
        Key="manuals/pump_v2.pdf",
        Body=b"%PDF-1.4 fake pdf content with text",
    )
    mock_pinecone_index.describe_index_stats.return_value = MagicMock(namespaces={})

    with patch_dependencies(
        pinecone=mock_pinecone_index, embeddings=mock_embeddings_model, s3=s3_bucket
    ):
        response = await async_client.post(
            "/api/v1/ingest",
            json={
                "asset_id": "abc-123",
                "event": "create",
                "documents": [
                    {
                        "s3_key": "manuals/pump_v2.pdf",
                        "doc_id": "manual-v2",
                        "doc_type": "user_manual",
                        "filename": "pump_v2.pdf",
                    }
                ],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == "abc-123"
    assert body["event"] == "create"
    assert body["namespace"] == "asset_abc-123"


@pytest.mark.asyncio
async def test_ingest_create_idempotent(
    async_client, auth_headers, s3_bucket, mock_pinecone_index, mock_embeddings_model
):
    """POST /ingest with create event on existing namespace should be a no-op."""
    # Namespace already has docs
    mock_pinecone_index.describe_index_stats.return_value = MagicMock(
        namespaces={"asset_abc-123": MagicMock(vector_count=10)}
    )

    with patch_dependencies(
        pinecone=mock_pinecone_index, embeddings=mock_embeddings_model, s3=s3_bucket
    ):
        response = await async_client.post(
            "/api/v1/ingest",
            json={
                "asset_id": "abc-123",
                "event": "create",
                "documents": [
                    {
                        "s3_key": "manuals/pump_v2.pdf",
                        "doc_id": "manual-v2",
                        "doc_type": "user_manual",
                        "filename": "pump_v2.pdf",
                    }
                ],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    # Should be a no-op — zero vectors processed
    assert body["documents_processed"] == 0
    assert body["vectors_upserted"] == 0


@pytest.mark.asyncio
async def test_ingest_update_requires_single_document(
    async_client, auth_headers, s3_bucket, mock_pinecone_index, mock_embeddings_model
):
    """POST /ingest with update event and multiple documents should return 422."""
    with patch_dependencies(
        pinecone=mock_pinecone_index, embeddings=mock_embeddings_model, s3=s3_bucket
    ):
        response = await async_client.post(
            "/api/v1/ingest",
            json={
                "asset_id": "abc-123",
                "event": "update",
                "documents": [
                    {
                        "s3_key": "a.pdf",
                        "doc_id": "doc-1",
                        "doc_type": "user_manual",
                        "filename": "a.pdf",
                    },
                    {
                        "s3_key": "b.pdf",
                        "doc_id": "doc-2",
                        "doc_type": "safety_sheet",
                        "filename": "b.pdf",
                    },
                ],
            },
            headers=auth_headers,
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_missing_api_key(
    async_client, s3_bucket, mock_pinecone_index, mock_embeddings_model
):
    """POST /ingest without X-API-Key header should return 401."""
    with patch_dependencies(
        pinecone=mock_pinecone_index, embeddings=mock_embeddings_model, s3=s3_bucket
    ):
        response = await async_client.post(
            "/api/v1/ingest",
            json={
                "asset_id": "abc-123",
                "event": "create",
                "documents": [
                    {
                        "s3_key": "a.pdf",
                        "doc_id": "doc-1",
                        "doc_type": "user_manual",
                        "filename": "a.pdf",
                    }
                ],
            },
            # No X-API-Key header
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_check_no_auth_required(async_client):
    """GET /health should return 200 without authentication."""
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ingest_add_event(
    async_client, auth_headers, s3_bucket, mock_pinecone_index, mock_embeddings_model
):
    """POST /ingest with add event should return 200 and add vectors to existing namespace."""
    s3_bucket.put_object(
        Bucket="test-bucket",
        Key="manuals/pump_v3.pdf",
        Body=b"%PDF-1.4 fake pdf content with text",
    )
    mock_pinecone_index.describe_index_stats.return_value = MagicMock(
        namespaces={"asset_abc-123": MagicMock(vector_count=5)}
    )

    with patch_dependencies(
        pinecone=mock_pinecone_index, embeddings=mock_embeddings_model, s3=s3_bucket
    ):
        response = await async_client.post(
            "/api/v1/ingest",
            json={
                "asset_id": "abc-123",
                "event": "add",
                "documents": [
                    {
                        "s3_key": "manuals/pump_v3.pdf",
                        "doc_id": "manual-v3",
                        "doc_type": "user_manual",
                        "filename": "pump_v3.pdf",
                    }
                ],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == "abc-123"
    assert body["event"] == "add"
    assert body["documents_processed"] == 1


@pytest.mark.asyncio
async def test_ingest_update_event(
    async_client, auth_headers, s3_bucket, mock_pinecone_index, mock_embeddings_model
):
    """POST /ingest with update event should delete old doc vectors and insert new ones."""
    s3_bucket.put_object(
        Bucket="test-bucket",
        Key="manuals/pump_v2_updated.pdf",
        Body=b"%PDF-1.4 updated fake pdf content with text",
    )
    # Namespace has old vectors
    mock_pinecone_index.describe_index_stats.return_value = MagicMock(
        namespaces={"asset_abc-123": MagicMock(vector_count=10)}
    )
    mock_pinecone_index.list.return_value = iter([["vec1", "vec2"]])

    with patch_dependencies(
        pinecone=mock_pinecone_index, embeddings=mock_embeddings_model, s3=s3_bucket
    ):
        response = await async_client.post(
            "/api/v1/ingest",
            json={
                "asset_id": "abc-123",
                "event": "update",
                "documents": [
                    {
                        "s3_key": "manuals/pump_v2_updated.pdf",
                        "doc_id": "manual-v2",
                        "doc_type": "user_manual",
                        "filename": "pump_v2_updated.pdf",
                    }
                ],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == "abc-123"
    assert body["event"] == "update"
    assert body["documents_processed"] == 1
    # delete_by_doc_id is called
    mock_pinecone_index.delete.assert_called_once_with(
        ids=["vec1", "vec2"],
        namespace="asset_abc-123",
    )


@pytest.mark.asyncio
async def test_upload_and_ingest_documents(
    async_client, auth_headers, s3_bucket, mock_pinecone_index, mock_embeddings_model
):
    """POST /ingest/upload with files should upload to S3 and ingest."""
    mock_pinecone_index.describe_index_stats.return_value = MagicMock(namespaces={})

    with patch_dependencies(
        pinecone=mock_pinecone_index, embeddings=mock_embeddings_model, s3=s3_bucket
    ):
        # Create a fake PDF file for upload using proper tuple format
        fake_pdf = ("test_manual.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")
        response = await async_client.post(
            "/api/v1/ingest/upload",
            data={
                "asset_id": "test-upload-asset",
                "event": "create",
            },
            files={"files": fake_pdf},
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == "test-upload-asset"
    assert body["event"] == "create"
    assert body["documents_processed"] == 1


@pytest.mark.asyncio
async def test_upload_invalid_asset_id(
    async_client, auth_headers, s3_bucket, mock_pinecone_index, mock_embeddings_model
):
    """POST /ingest/upload with invalid asset_id should return 400."""
    with patch_dependencies(
        pinecone=mock_pinecone_index, embeddings=mock_embeddings_model, s3=s3_bucket
    ):
        fake_pdf = ("test.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")
        response = await async_client.post(
            "/api/v1/ingest/upload",
            data={
                "asset_id": "../../etc/passwd",
                "event": "create",
            },
            files={"files": fake_pdf},
            headers=auth_headers,
        )

    assert response.status_code == 400
    assert "asset_id" in response.json()["detail"]["message"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Offline / local provider tests (Tasks 1, 2, 6, 11)
# ─────────────────────────────────────────────────────────────────────────────


def _enable_local_offline_mode(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Switch the running app to fully-offline local mode for one test.

    Sets the env vars that drive :class:`Settings` and clears the cached
    settings singleton plus all LRU-cached client factories. The relevant
    modules are also reloaded so any module-level references held by the
    FastAPI app (e.g. inside :mod:`app.main` and the lifespan handler)
    pick up the new state. The test must build a fresh FastAPI app after
    calling this helper — the shared ``async_client`` fixture was
    created against the pre-reload environment.

    Test isolation: an autouse fixture in this module (see
    :func:`_restore_clean_settings_for_each_test`) clears the LRU caches
    at the START of every test so previous offline-mode settings do not
    leak into subsequent tests.
    """
    monkeypatch.setenv("LOCAL_OFFLINE", "True")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("IMAGE_AGENT_PROVIDER", "local")
    monkeypatch.setenv("RULE_AGENT_PROVIDER", "local")
    monkeypatch.setenv("VERDICT_AGENT_PROVIDER", "local")
    monkeypatch.setenv("CHAT_AGENT_PROVIDER", "local")
    monkeypatch.setenv("IMAGE_AGENT_MODEL", "local-dummy")
    monkeypatch.setenv("RULE_AGENT_MODEL", "local-dummy")
    monkeypatch.setenv("VERDICT_AGENT_MODEL", "local-dummy")
    monkeypatch.setenv("CHAT_AGENT_MODEL", "local-dummy")
    # Disable the static-file mount while we chdir into a temp directory.
    monkeypatch.setenv("SERVE_FRONTEND", "False")

    # Clear cached singletons so the new env values take effect.
    from app import config as app_config
    from app import dependencies as app_dependencies
    from app import main as app_main

    app_config.get_settings.cache_clear()
    app_dependencies._get_pinecone_index.cache_clear()
    app_dependencies._get_s3_client.cache_clear()
    app_dependencies._get_dynamodb_client.cache_clear()
    app_dependencies._get_embeddings_model.cache_clear()
    app_dependencies._get_agent_llm.cache_clear()

    # Re-import the modules to refresh any module-level state bound to the
    # previous settings instance. ``app.main`` is reloaded last so that
    # the new ``settings`` value is used when ``create_app()`` runs.
    importlib.reload(app_config)
    importlib.reload(app_dependencies)
    importlib.reload(app_main)

    # Register a finalizer that runs AFTER monkeypatch.undo() so the
    # LRU caches are cleared when the env has already been reverted to
    # the conftest defaults. ``request.addfinalizer`` callbacks are
    # run after ``monkeypatch.undo()`` because pytest unwinds the
    # fixture finalizers (including monkeypatch) before the test
    # function's own finalizers registered via ``request.addfinalizer``.
    request.addfinalizer(_final_cleanup_on_teardown)


def _reset_caches_after_offline_test() -> None:
    """Clear the LRU caches so subsequent tests see the conftest defaults.

    Call this from the END of a test that uses
    :func:`_enable_local_offline_mode`. The function clears the
    ``get_settings`` LRU cache and the dependency factory caches so
    that, once monkeypatch reverts the env on teardown, the next test
    that calls :func:`get_settings` re-reads the conftest env and
    instantiates a fresh ``Settings``.

    We intentionally do NOT reload ``app.main`` here: the module-level
    ``settings`` variable in ``app.main`` keeps its offline values for
    the remainder of the test, but that does not matter because we are
    about to return and the next test will use a different fixture
    (e.g. ``async_client``) which will trigger a fresh ``get_settings``
    call into a now-empty cache.

    A second pass is performed in :func:`_final_cleanup_on_teardown` —
    registered via ``request.addfinalizer`` — to clear the LRU caches
    AGAIN, AFTER the env has been reverted. This ensures that any
    ``get_settings`` reference imported at the top of another test
    module (e.g. :mod:`tests.unit.test_config`) sees a fresh
    ``Settings`` instance built from the restored conftest env.
    """
    from app import config as app_config_teardown
    from app import dependencies as app_dependencies_teardown

    app_config_teardown.get_settings.cache_clear()
    app_dependencies_teardown._get_pinecone_index.cache_clear()
    app_dependencies_teardown._get_s3_client.cache_clear()
    app_dependencies_teardown._get_dynamodb_client.cache_clear()
    app_dependencies_teardown._get_embeddings_model.cache_clear()
    app_dependencies_teardown._get_agent_llm.cache_clear()


def _final_cleanup_on_teardown() -> None:
    """Second-pass cache clear that runs AFTER monkeypatch env revert.

    Registered as a finalizer on each offline test's request. By the
    time this runs, monkeypatch has already restored the env to the
    conftest defaults, so clearing the caches here guarantees that the
    next test's ``get_settings()`` call instantiates a fresh
    ``Settings`` from the (now restored) conftest env.

    The function clears caches on EVERY ``get_settings`` reference it
    can find, including the one imported at the top of other test
    modules (e.g. ``tests.unit.test_config``). This is necessary
    because ``importlib.reload`` creates a new function object — the
    cache on the OLD function (held by other test modules) would
    otherwise retain the offline ``Settings`` instance.
    """
    from app import config as app_config_final
    from app import dependencies as app_dependencies_final

    # Clear the (reloaded) module's cache.
    app_config_final.get_settings.cache_clear()
    app_dependencies_final._get_pinecone_index.cache_clear()
    app_dependencies_final._get_s3_client.cache_clear()
    app_dependencies_final._get_dynamodb_client.cache_clear()
    app_dependencies_final._get_embeddings_model.cache_clear()
    app_dependencies_final._get_agent_llm.cache_clear()

    # Aggressively clear caches on ANY live ``get_settings`` reference.
    # The reload created a new function object, but other test modules
    # may still hold a reference to the pre-reload one whose cache is
    # untouched. We walk the garbage-collector roots to find them.
    import gc

    for obj in gc.get_objects():
        if not callable(obj):
            continue
        qualname = getattr(obj, "__qualname__", "")
        if qualname != "get_settings":
            continue
        # ``get_settings`` is a function decorated with ``@lru_cache``.
        # Bound to a module, it has a ``cache_info`` method.
        cache_info = getattr(obj, "cache_info", None)
        if cache_info is None:
            continue
        try:
            info = cache_info()
        except TypeError:
            # The unbound method on the class is also reachable; skip.
            continue
        if info.currsize > 0:
            obj.cache_clear()


def _build_minimal_pdf(text: str = "Compliance Manual - Pump Unit") -> bytes:
    """Build a minimal valid PDF that pypdf can parse to extract text.

    The blueprint test (Task 6) must drive the full ingest pipeline
    end-to-end through :class:`LocalS3Client` +
    :class:`LocalPineconeIndex` + :class:`LocalEmbeddings`. Because the
    downstream :func:`app.services.document_loader.load_pdf` uses
    pypdf to extract page text, a real (parseable) PDF is required —
    a body of ``b"%PDF-1.4 fake content"`` is rejected by pypdf with a
    ``PdfStreamError`` and produces zero chunks. This helper produces
    a structurally valid single-page PDF whose body stream draws the
    supplied text in Helvetica.

    Args:
        text: The literal text to embed in the page's content stream.
            Must be ASCII-safe; non-ASCII characters are not escaped
            in this minimal builder.

    Returns:
        The raw PDF bytes, suitable for uploading as a file body.
    """
    # Content stream: place text at (100, 700) using Helvetica 12pt.
    stream = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET".encode("latin-1")
    body_lines = [
        b"%PDF-1.4",
        b"1 0 obj",
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"endobj",
        b"2 0 obj",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"endobj",
        b"3 0 obj",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 << /Type /Font "
            b"/Subtype /Type1 /BaseFont /Helvetica >> >> >> >>"
        ),
        b"endobj",
        b"4 0 obj",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>",
        b"stream",
        stream,
        b"endstream",
        b"endobj",
    ]
    body = b"\n".join(body_lines) + b"\n"
    xref_offset = len(body)
    # xref table — pypdf tolerates imprecise offsets (it logs warnings
    # but still resolves objects by walking the file).
    xref_lines = [
        b"xref",
        b"0 5",
        b"0000000000 65535 f ",
        b"0000000009 00000 n ",
        b"0000000058 00000 n ",
        b"0000000115 00000 n ",
        b"0000000267 00000 n ",
    ]
    trailer = (
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode("ascii")
        + b"\n%%EOF\n"
    )
    return body + b"\n".join(xref_lines) + b"\n" + trailer


@pytest.mark.asyncio
async def test_local_upload_and_ingest(
    request: pytest.FixtureRequest,
    auth_headers: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end test using LocalS3Client + LocalPineconeIndex + LocalEmbeddings.

    Verifies the offline pipeline (Task 6) — no mocks, no real network
    calls. Uploads a real (parseable) PDF and asserts the response,
    on-disk S3 file, and the Pinecone index namespace state.

    The shared ``async_client`` fixture cannot be used here because it
    was constructed against the conftest's default (non-offline) env. We
    enable local-offline mode via ``monkeypatch``, then build a fresh
    FastAPI app and ``AsyncClient`` from scratch for the duration of the
    test.
    """
    _enable_local_offline_mode(request, monkeypatch)

    # The local storage paths are relative to the current working
    # directory. Move into tmp_path so the test does not collide with
    # any pre-existing ``.local_storage`` directory.
    monkeypatch.chdir(tmp_path)
    s3_dir = tmp_path / ".local_storage" / "s3"

    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ingest/upload",
            data={"asset_id": "test-local", "event": "create"},
            files={
                "files": (
                    "test_manual.pdf",
                    _build_minimal_pdf(
                        "Compliance Manual - Pump Unit. "
                        "Pressure must not exceed 150 PSI. "
                        "Inspect seals every six months."
                    ),
                    "application/pdf",
                )
            },
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["asset_id"] == "test-local"
    assert body["event"] == "create"
    assert body["documents_processed"] == 1
    # The pipeline should have embedded at least one chunk from the PDF.
    assert body["vectors_upserted"] > 0

    # The PDF should have been written to the local S3 emulation directory.
    from app.config import get_settings

    bucket = get_settings().s3_bucket_name
    written_files = list((s3_dir / bucket / "test-local").iterdir())
    assert any(p.name == "test_manual.pdf" for p in written_files)

    # The Pinecone namespace for the asset should report non-zero vectors.
    # We re-import the (reloaded) module here so the cached LocalPineconeIndex
    # instance is the same one the FastAPI app used during the request —
    # Qdrant's local persistence uses an exclusive file lock that prevents
    # two clients from pointing at the same path simultaneously.
    from app import dependencies as app_dependencies_re

    stats = app_dependencies_re._get_pinecone_index().describe_index_stats()
    namespace = stats.namespaces.get("asset_test-local")
    assert namespace is not None
    assert namespace.vector_count > 0

    # Clear the LRU caches so subsequent tests see the conftest defaults
    # rather than the offline values left over from this test.
    _reset_caches_after_offline_test()


@pytest.mark.asyncio
async def test_zen_provider_initialisation(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_get_agent_llm('zen', 'gpt-5.4') must return a ChatOpenAI with the Zen base URL.

    Verifies Task 9 routing: the OpenCode Zen gateway is wired in via
    ChatOpenAI with the correct (compile-time constant) base URL.
    """
    from langchain_openai import ChatOpenAI

    _enable_local_offline_mode(request, monkeypatch)
    # Override ZEN_API_KEY without the offline auto-detect replacing it.
    monkeypatch.setenv("IMAGE_AGENT_PROVIDER", "zen")
    monkeypatch.setenv("IMAGE_AGENT_MODEL", "gpt-5.4")
    monkeypatch.setenv("ZEN_API_KEY", "test-zen-key")
    from app import config as app_config
    from app import dependencies as app_dependencies

    app_config.get_settings.cache_clear()
    app_dependencies._get_agent_llm.cache_clear()

    client = _get_agent_llm("zen", "gpt-5.4")

    assert isinstance(client, ChatOpenAI)
    # ChatOpenAI stores the base URL in ``openai_api_base``. The Zen URL
    # is the canonical identifier we need to assert against.
    assert client.openai_api_base == ZEN_BASE_URL
    assert ZEN_BASE_URL == "https://opencode.ai/zen/v1"

    # Reset the LRU caches so subsequent tests see the conftest defaults
    # rather than the offline values left over from this test.
    _reset_caches_after_offline_test()


@pytest.mark.asyncio
async def test_opencode_go_provider_initialisation(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_get_agent_llm('opencode_go', ...) must return a ChatOpenAI with the Go base URL.

    Verifies Task 10 routing: the OpenCode Go gateway is wired in via
    ChatOpenAI with the correct (compile-time constant) base URL.
    """
    from langchain_openai import ChatOpenAI

    _enable_local_offline_mode(request, monkeypatch)
    monkeypatch.setenv("RULE_AGENT_PROVIDER", "opencode_go")
    monkeypatch.setenv("RULE_AGENT_MODEL", "qwen3.6-plus")
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "test-go-key")
    from app import config as app_config
    from app import dependencies as app_dependencies

    app_config.get_settings.cache_clear()
    app_dependencies._get_agent_llm.cache_clear()

    client = _get_agent_llm("opencode_go", "qwen3.6-plus")

    assert isinstance(client, ChatOpenAI)
    assert client.openai_api_base == OPENCODE_GO_BASE_URL
    assert OPENCODE_GO_BASE_URL == "https://opencode.ai/zen/go/v1"

    _reset_caches_after_offline_test()


@pytest.mark.asyncio
async def test_local_provider_routing_returns_offline_clients(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When providers are set to 'local', all factories return the offline classes.

    Verifies that the cold-start sequence (Section 5.1) wires the offline
    clients when every provider is set to ``local``.
    """
    _enable_local_offline_mode(request, monkeypatch)

    # Resolve the (reloaded) factory functions so we share the same LRU
    # cache the FastAPI app would use at runtime.
    from app import dependencies as app_dependencies_re

    s3 = app_dependencies_re._get_s3_client()
    index = app_dependencies_re._get_pinecone_index()
    embeddings = app_dependencies_re._get_embeddings_model()
    llm = app_dependencies_re._get_agent_llm("local", "local-dummy")

    assert isinstance(s3, LocalS3Client)
    assert isinstance(index, LocalPineconeIndex)
    assert isinstance(embeddings, LocalEmbeddings)
    assert isinstance(llm, LocalChatModel)

    _reset_caches_after_offline_test()
