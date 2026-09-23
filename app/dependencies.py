"""
FastAPI dependency injection providers.

All external clients are initialised once per Lambda cold start and
reused across requests via module-level LRU-cached singletons.
FastAPI's Depends() system injects them cleanly into route handlers.

Pattern: private `_get_*` functions are cached at the module level;
public `get_*` wrappers are the FastAPI Depends targets.

Provider resolution
-------------------

The chat-model factory routes to the correct backend based on the
configured provider string:

- ``openrouter`` — OpenAI-compatible ``ChatOpenAI`` against the OpenRouter gateway
- ``zen`` — OpenAI-compatible ``ChatOpenAI`` against the OpenCode Zen gateway
- ``opencode_go`` — OpenAI-compatible ``ChatOpenAI`` against the OpenCode Go gateway
- ``xai`` / ``grok`` — Native ``ChatXAI`` against xAI
- ``local`` — ``LocalChatModel`` returning canned responses (offline dev only)
- anything else — falls through to ``init_chat_model`` for native LangChain routing

The embeddings factory adds a ``local`` branch that returns a
:class:`LocalEmbeddings` instance, and keeps the existing
``init_embeddings`` behaviour for ``openai``/``anthropic``/``google_genai``.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

import boto3
import structlog
from fastapi import Depends
from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from pinecone import Index, Pinecone
from pydantic import SecretStr

from app.config import Settings, get_settings
from app.utils.offline_clients import (
    LocalChatModel,
    LocalDynamoDBClient,
    LocalEmbeddings,
    LocalPineconeIndex,
    LocalS3Client,
)

logger = structlog.get_logger(__name__)

# OpenCode Zen is an OpenAI-compatible chat gateway. The base URL is a
# compile-time constant (NOT configurable via env var) to prevent SSRF.
ZEN_BASE_URL: str = "https://opencode.ai/zen/v1"

# OpenCode Go is the lower-cost subscription gateway. Same security posture.
OPENCODE_GO_BASE_URL: str = "https://opencode.ai/zen/go/v1"

# OpenRouter gateway base URL (pinned to keep parity with the existing
# implementation — moving it to config is out of scope for this blueprint).
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# Maximum supported embedding vector dimension. Must stay in sync with
# the validation in ``LocalEmbeddings`` and ``Settings.embedding_dimensions``.
_MAX_EMBEDDING_DIMENSIONS: int = 8192
_MIN_EMBEDDING_DIMENSIONS: int = 1


# ── Singleton client factories ─────────────────────────────────────────────


@lru_cache
def _get_pinecone_index() -> Index:
    """Initialise and cache the Pinecone index client."""
    settings = get_settings()
    if settings.local_offline:
        logger.info("local_offline_pinecone_initialised")
        return LocalPineconeIndex(Path(".local_storage/qdrant"), settings.embedding_dimensions)
    pc = Pinecone(api_key=settings.pinecone_api_key.get_secret_value())
    index: Index = pc.Index(settings.pinecone_index_name)
    logger.info("pinecone_client_initialised", index=settings.pinecone_index_name)
    return index


def _get_api_key(provider: str, settings: Settings) -> SecretStr | None:
    """Resolve the API key for a given provider from the settings store.

    Returns ``None`` if the provider has no key configured. Returning
    ``None`` (rather than raising) lets the downstream LLM initialiser
    decide whether to fail or fall back to environment variables — this
    matches the behaviour expected by the existing fallback path in
    :func:`_get_agent_llm`.

    Provider keys handled:

    - ``anthropic`` → ``Settings.anthropic_api_key``
    - ``openai`` → ``Settings.openai_api_key``
    - ``google_genai`` → ``Settings.google_api_key``
    - ``xai`` / ``grok`` → ``Settings.xai_api_key``
    - ``openrouter`` → ``Settings.openrouter_api_key``
    - ``zen`` → ``Settings.zen_api_key`` (new)
    - ``opencode_go`` → ``Settings.opencode_go_api_key`` (new)
    - ``local`` → ``None`` (no remote call is made)
    """
    if provider == "anthropic" and settings.anthropic_api_key:
        return settings.anthropic_api_key
    if provider == "openai" and settings.openai_api_key:
        return settings.openai_api_key
    if provider == "google_genai" and settings.google_api_key:
        return settings.google_api_key
    if provider in ("xai", "grok") and settings.xai_api_key:
        return settings.xai_api_key
    if provider == "openrouter" and settings.openrouter_api_key:
        return settings.openrouter_api_key
    if provider == "zen" and settings.zen_api_key:
        return settings.zen_api_key
    if provider == "opencode_go" and settings.opencode_go_api_key:
        return settings.opencode_go_api_key
    return None


@lru_cache
def _get_agent_llm(provider: str, model: str) -> BaseChatModel:
    """Initialise and cache a generic ``BaseChatModel`` for a specific agent.

    Routes the call to the correct backend based on ``provider``:

    - ``openrouter`` → ``ChatOpenAI`` against OpenRouter
    - ``zen`` → ``ChatOpenAI`` against OpenCode Zen
    - ``opencode_go`` → ``ChatOpenAI`` against OpenCode Go
    - ``xai`` / ``grok`` → ``ChatXAI``
    - ``local`` → :class:`LocalChatModel` (offline-only)
    - fallback → ``init_chat_model`` (delegates to LangChain's built-in
      provider routing for ``openai``/``anthropic``/``google_genai``/etc.)

    The factory is wrapped in :func:`functools.lru_cache` so each unique
    ``(provider, model)`` pair is created exactly once per process. Provider
    changes therefore require an application restart — this is intentional
    and matches the cold-start caching model used by the rest of the app.
    """
    settings = get_settings()
    api_key = _get_api_key(provider, settings)

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        client = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
        )
        logger.info("llm_client_initialised", provider=provider, model=model)
        return client

    if provider == "zen":
        from langchain_openai import ChatOpenAI

        client = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=ZEN_BASE_URL,
        )
        logger.info("llm_client_initialised", provider=provider, model=model)
        return client

    if provider == "opencode_go":
        from langchain_openai import ChatOpenAI

        client = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=OPENCODE_GO_BASE_URL,
        )
        logger.info("llm_client_initialised", provider=provider, model=model)
        return client

    if provider in ("xai", "grok"):
        from langchain_xai import ChatXAI

        client_xai = ChatXAI(
            model=model,
            api_key=api_key,
        )
        logger.info("llm_client_initialised", provider=provider, model=model)
        return client_xai

    if provider == "local":
        client_local = LocalChatModel(model_name=model)
        logger.info("llm_client_initialised", provider=provider, model=model)
        return client_local

    # init_chat_model will fallback to os.environ if api_key is None
    kwargs = {"api_key": api_key} if api_key else {}

    client_init = init_chat_model(  # type: ignore[call-overload]
        model=model, model_provider=provider, **kwargs
    )
    logger.info("llm_client_initialised", provider=provider, model=model)
    return client_init  # type: ignore[no-any-return]


@lru_cache
def _get_embeddings_model() -> Embeddings:
    """Initialise and cache the generic embeddings model.

    Branches:

    - ``local`` → :class:`LocalEmbeddings` returning deterministic zero-vectors
    - ``openai`` / ``anthropic`` → :func:`init_embeddings` with the configured key
    - any other provider → :func:`init_embeddings` (LangChain-native routing)
    """
    settings = get_settings()
    provider = settings.embedding_provider
    api_key = _get_api_key(provider, settings)

    if provider == "local":
        dimensions = settings.embedding_dimensions
        if dimensions < _MIN_EMBEDDING_DIMENSIONS or dimensions > _MAX_EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"embedding_dimensions must be between "
                f"{_MIN_EMBEDDING_DIMENSIONS} and {_MAX_EMBEDDING_DIMENSIONS}, "
                f"got {dimensions}"
            )
        local_embeddings = LocalEmbeddings(dimensions=dimensions)
        logger.info("local_embeddings_initialised", dimensions=dimensions)
        return local_embeddings

    kwargs = {"api_key": api_key} if api_key else {}

    embeddings = init_embeddings(model=settings.embedding_model, provider=provider, **kwargs)
    logger.info("embeddings_initialised", provider=provider, model=settings.embedding_model)
    return embeddings  # type: ignore[return-value]


@lru_cache
def _get_s3_client() -> Any:  # boto3 clients are not generically typed
    """Initialise and cache the boto3 S3 client."""
    settings = get_settings()
    if settings.local_offline:
        logger.info("local_offline_s3_initialised")
        return LocalS3Client(Path(".local_storage/s3"))
    client = boto3.client("s3", region_name=settings.aws_region)
    logger.info("s3_client_initialised", region=settings.aws_region)
    return client


@lru_cache
def _get_dynamodb_client() -> Any:  # boto3 clients are not generically typed
    """Initialise and cache the boto3 DynamoDB client."""
    settings = get_settings()
    if settings.local_offline:
        logger.info("local_offline_dynamodb_initialised")
        return LocalDynamoDBClient(Path(".local_storage/dynamodb.db"))
    client = boto3.client("dynamodb", region_name=settings.aws_region)
    logger.info("dynamodb_client_initialised", region=settings.aws_region)
    return client


# ── FastAPI Depends providers ─────────────────────────────────────────────


def get_pinecone_index() -> Index:
    """FastAPI dependency: returns the cached Pinecone index."""
    return _get_pinecone_index()


def get_image_agent_llm() -> BaseChatModel:
    """FastAPI dependency: returns the cached LLM for the image agent."""
    settings = get_settings()
    return _get_agent_llm(settings.image_agent_provider, settings.image_agent_model)


def get_rule_agent_llm() -> BaseChatModel:
    """FastAPI dependency: returns the cached LLM for the rule agent."""
    settings = get_settings()
    return _get_agent_llm(settings.rule_agent_provider, settings.rule_agent_model)


def get_verdict_agent_llm() -> BaseChatModel:
    """FastAPI dependency: returns the cached LLM for the verdict agent."""
    settings = get_settings()
    return _get_agent_llm(settings.verdict_agent_provider, settings.verdict_agent_model)


def get_chat_agent_llm() -> BaseChatModel:
    """FastAPI dependency: returns the cached LLM for the chat agent."""
    settings = get_settings()
    return _get_agent_llm(settings.chat_agent_provider, settings.chat_agent_model)


def get_embeddings() -> Embeddings:
    """FastAPI dependency: returns the cached Embeddings model."""
    return _get_embeddings_model()


def get_s3_client() -> Any:
    """FastAPI dependency: returns the cached S3 client."""
    return _get_s3_client()


def get_dynamodb_client() -> Any:
    """FastAPI dependency: returns the cached DynamoDB client."""
    return _get_dynamodb_client()


# ── Typed dependency aliases for route signatures ─────────────────────────

PineconeDep = Annotated[Index, Depends(get_pinecone_index)]
ImageLLMDep = Annotated[BaseChatModel, Depends(get_image_agent_llm)]
RuleLLMDep = Annotated[BaseChatModel, Depends(get_rule_agent_llm)]
VerdictLLMDep = Annotated[BaseChatModel, Depends(get_verdict_agent_llm)]
ChatLLMDep = Annotated[BaseChatModel, Depends(get_chat_agent_llm)]
EmbeddingsDep = Annotated[Embeddings, Depends(get_embeddings)]
S3Dep = Annotated[Any, Depends(get_s3_client)]
DynamoDBDep = Annotated[Any, Depends(get_dynamodb_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
