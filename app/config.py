"""
Application settings loaded from environment variables.

All external API keys, model names, and configuration values are read
from the environment — never hardcoded. SecretStr fields prevent secrets
from appearing in logs, tracebacks, or serialised model output.

Usage:
    from app.config import get_settings
    settings = get_settings()  # cached singleton per process
"""

from functools import lru_cache
from typing import Literal, Self

import structlog
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

# Placeholder API key values commonly found in example ``.env`` files. The
# auto-detect validator (see :meth:`Settings.validate_local_provider_defaults`)
# uses this set to detect "obvious" placeholders and switch the corresponding
# provider to ``local`` so that the application runs end-to-end without real
# credentials.
_PLACEHOLDER_API_KEY_VALUES: frozenset[str] = frozenset(
    {
        "sk-proj-xxx",
        "sk-ant-xxx",
        "sk-or-v1-...",
        "your-pinecone-api-key",
        "your-xai-grok-api-key",
        "your-shared-secret-key-min-32-chars",
        "your-langsmith-api-key",
        "your-opencode-zen-api-key",
        "your-opencode-go-api-key",
    }
)

# Map an LLM provider string to the matching ``Settings`` attribute that
# holds its API key. Used by the auto-detect validator to look up the
# configured key for each agent's provider.
_PROVIDER_API_KEY_FIELD: dict[str, str] = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "google_genai": "google_api_key",
    "xai": "xai_api_key",
    "grok": "xai_api_key",
    "openrouter": "openrouter_api_key",
    "zen": "zen_api_key",
    "opencode_go": "opencode_go_api_key",
}

# Agent provider field names. Each tuple is ``(provider_field, model_field)``.
_AGENT_FIELDS: tuple[tuple[str, str], ...] = (
    ("image_agent_provider", "image_agent_model"),
    ("rule_agent_provider", "rule_agent_model"),
    ("verdict_agent_provider", "verdict_agent_model"),
    ("chat_agent_provider", "chat_agent_model"),
)


class Settings(BaseSettings):
    """Validated application settings sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Extra fields are ignored, not rejected — allows future env var additions
        # without breaking existing deployments.
        extra="ignore",
    )

    # ── Local Offline Mode ────────────────────────────────────────────────────
    local_offline: bool = Field(default=False, description="Enable local offline development mode")
    serve_frontend: bool = Field(
        default=True, description="Serve frontend static assets from FastAPI"
    )

    # ── AWS ───────────────────────────────────────────────────────────────────
    aws_region: str = Field(default="us-east-1", description="AWS region for all SDK calls")
    s3_bucket_name: str = Field(
        default="local-bucket", description="S3 bucket holding asset documents and images"
    )

    # ── Pinecone ──────────────────────────────────────────────────────────────
    pinecone_api_key: SecretStr = Field(
        default=SecretStr("offline-dummy"), description="Pinecone API key"
    )
    pinecone_index_name: str = Field(
        default="local-index", description="Pinecone serverless index name"
    )
    pinecone_environment: str = Field(
        default="local", description="Pinecone cloud environment identifier"
    )

    # ── LLM Providers (API Keys) ──────────────────────────────────────────────
    anthropic_api_key: SecretStr | None = Field(default=None, description="Anthropic API key")
    openai_api_key: SecretStr | None = Field(default=None, description="OpenAI API key")
    google_api_key: SecretStr | None = Field(default=None, description="Google Gemini API key")
    xai_api_key: SecretStr | None = Field(default=None, description="xAI Grok API key")
    openrouter_api_key: SecretStr | None = Field(default=None, description="OpenRouter API key")
    zen_api_key: SecretStr | None = Field(
        default=None,
        description="OpenCode Zen API key (https://opencode.ai/zen)",
    )
    opencode_go_api_key: SecretStr | None = Field(
        default=None,
        description="OpenCode Go API key (https://opencode.ai/zen/go)",
    )

    # ── Reranking (Optional - local, free) ─────────────────────────────────────
    rerank_enabled: bool = Field(
        default=False,
        description="Enable local reranking with FlashRank as a second-pass relevance filter",
    )
    rerank_model: str = Field(
        default="ms-marco-MiniLM-L-12-v2",
        description=(
            "FlashRank model identifier. Options: "
            "ms-marco-TinyBERT-L-2 (~4MB), "
            "ms-marco-MiniLM-L-12-v2 (~34MB, recommended), "
            "rank-T5-flan (~110MB)"
        ),
    )
    rerank_max_length: int = Field(
        default=128,
        ge=32,
        le=512,
        description="Max sequence length for reranker (lower = faster, adjust based on chunk size)",
    )
    rerank_top_n: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of candidates passed to the reranker",
    )

    # ── Agent Configuration ───────────────────────────────────────────────────
    image_agent_provider: str = Field(default="openai", description="LLM provider for image agent")
    image_agent_model: str = Field(default="gpt-4o", description="Model for image agent")

    rule_agent_provider: str = Field(default="openai", description="LLM provider for rule agent")
    rule_agent_model: str = Field(default="gpt-4o", description="Model for rule agent")

    verdict_agent_provider: str = Field(
        default="openai", description="LLM provider for verdict agent"
    )
    verdict_agent_model: str = Field(default="gpt-4o", description="Model for verdict agent")

    chat_agent_provider: str = Field(default="openai", description="LLM provider for chat agent")
    chat_agent_model: str = Field(default="gpt-4o", description="Model for chat agent")

    # ── LLM Max Tokens ────────────────────────────────────────────────────────
    llm_max_tokens: int = Field(
        default=4096,
        ge=1,
        le=8192,
        description="Max tokens for audit verdict generation",
    )
    llm_chat_max_tokens: int = Field(
        default=1024,
        ge=1,
        le=4096,
        description="Max tokens for chat responses",
    )

    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_provider: str = Field(
        default="openai",
        description=(
            "Embedding provider name. Valid values: openai, anthropic, "
            "google_genai, local. The 'local' value uses the deterministic "
            "offline LocalEmbeddings provider."
        ),
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model name — change via env var without code changes",
    )
    embedding_dimensions: int = Field(
        default=1536,
        ge=1,
        le=8192,
        description="Embedding vector dimensions — must match Pinecone index configuration",
    )
    embedding_batch_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Number of texts embedded per API call to stay within rate limits",
    )

    # ── LangSmith (optional tracing) ──────────────────────────────────────────
    langchain_tracing_v2: bool = Field(default=False, description="Enable LangSmith tracing")
    langchain_api_key: SecretStr | None = Field(
        default=None, description="LangSmith API key (optional)"
    )
    langchain_project: str = Field(
        default="asset-compliance-ai", description="LangSmith project name"
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", description="Deployment environment"
    )
    log_level: str = Field(default="INFO", description="Logging level")
    cors_allowed_origins: list[str] = Field(
        default=["http://localhost:8000"],
        description=(
            "Allowed CORS origins. In production, set to your backend client domain(s) "
            "to prevent the wildcard + credentials CORS vulnerability. "
            'Example: CORS_ALLOWED_ORIGINS=["https://app.yourdomain.com"]'
        ),
    )
    retrieval_top_k_audit: int = Field(
        default=20, ge=1, le=100, description="Top-k chunks retrieved for audit queries"
    )
    retrieval_top_k_chat: int = Field(
        default=12, ge=1, le=50, description="Top-k chunks retrieved for chat queries"
    )
    chunk_size: int = Field(
        default=512, ge=64, le=4096, description="Document chunk size in characters"
    )
    chunk_overlap: int = Field(
        default=64, ge=0, le=512, description="Overlap between consecutive chunks in characters"
    )
    evidence_bundle_cap: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Max number of evidence items passed to verdict LLM and returned in API",
    )

    # ── Hybrid Search (BM25 + Dense) ─────────────────────────────────────────
    hybrid_search_enabled: bool = Field(
        default=True,
        description="Enable hybrid search combining BM25 sparse and dense vectors",
    )
    hybrid_alpha: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description=(
            "Weight for dense score in hybrid fusion. "
            "final_score = alpha * dense_score + (1 - alpha) * bm25_score"
        ),
    )
    bm25_k1: float = Field(
        default=1.5,
        ge=0.0,
        le=3.0,
        description="BM25 term frequency saturation parameter",
    )
    bm25_b: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="BM25 length normalization parameter",
    )

    # ── Parent-Document Retrieval (PDR) ───────────────────────────────────────
    pdr_enabled: bool = Field(
        default=True,
        description="Enable Parent-Document Retrieval for hierarchical context",
    )
    pdr_parent_chunk_size: int = Field(
        default=2048,
        ge=512,
        le=8192,
        description="Parent document chunk size in characters (larger context window)",
    )
    pdr_child_chunk_size: int = Field(
        default=256,
        ge=64,
        le=1024,
        description="Child chunk size in characters (smaller retrieval units)",
    )
    pdr_child_overlap: int = Field(
        default=32,
        ge=0,
        le=128,
        description="Overlap between consecutive child chunks in characters",
    )
    audit_timeout_seconds: int = Field(
        default=120,
        ge=10,
        le=800,
        description="Max time allowed for the audit graph execution before timing out",
    )
    node_timeout_seconds: int = Field(
        default=60,
        ge=5,
        le=300,
        description="Max time allowed for a single agent node before timing out",
    )

    # ── DynamoDB ──────────────────────────────────────────────────────────────
    dynamodb_audit_table: str = Field(
        default="local-audit-runs",
        description=(
            "DynamoDB table name used for audit run idempotency tracking. "
            "Populated automatically from CloudFormation via SAM env vars."
        ),
    )

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    # Format: "<count>/<period>" — e.g. "10/minute", "100/hour".
    # Enforced by slowapi on the Lambda Function URL ingress.
    rate_limit_audit: str = Field(
        default="10/minute",
        description="Max audit run requests per source IP per period",
    )
    rate_limit_ingest: str = Field(
        default="30/minute",
        description="Max ingest requests per source IP per period",
    )
    rate_limit_chat: str = Field(
        default="60/minute",
        description="Max chat query requests per source IP per period",
    )

    # ── Authentication ────────────────────────────────────────────────────────
    api_secret_key: SecretStr | None = Field(
        default=None,
        description=(
            "Shared API secret key. Must match the API_SECRET_KEY configured in the "
            "enterprise asset management system. All inbound requests must include the "
            "X-API-Key header with this value.  Required in staging and production."
        ),
    )

    @model_validator(mode="after")
    def validate_retrieval_settings(self) -> Self:
        """Validate retrieval settings whose constraints depend on another field."""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size.")
        if self.pdr_child_overlap >= self.pdr_child_chunk_size:
            raise ValueError("pdr_child_overlap must be less than pdr_child_chunk_size.")
        if self.pdr_child_chunk_size > self.pdr_parent_chunk_size:
            raise ValueError("pdr_child_chunk_size must not exceed pdr_parent_chunk_size.")
        return self

    @model_validator(mode="after")
    def validate_api_key(self) -> Self:
        """Require API_SECRET_KEY in staging and production environments."""
        if self.app_env in ("staging", "production") and self.api_secret_key is None:
            raise ValueError("API_SECRET_KEY must be set in staging and production environments.")
        return self

    @model_validator(mode="after")
    def validate_cors(self) -> Self:
        """Prevent wildcard CORS in production to mitigate SEC-1."""
        if self.app_env == "production":
            if "*" in self.cors_allowed_origins or ["*"] == self.cors_allowed_origins:
                raise ValueError("Wildcard CORS (['*']) is not allowed in production environments.")
        return self

    @model_validator(mode="after")
    def validate_local_provider_defaults(self) -> Self:
        """When ``local_offline`` is True, auto-switch provider strings to ``local``
        if the corresponding API key is missing or is a known placeholder.

        This makes local development friction-free: a user only needs to set
        ``LOCAL_OFFLINE=True`` and the application will route the embeddings
        and agent calls to the offline providers (``LocalEmbeddings`` and
        ``LocalChatModel``) instead of failing on the placeholder keys shipped
        with the example ``.env`` file.

        The auto-detect ONLY activates when ``local_offline`` is True. In
        staging and production the configured providers are left untouched
        so that any missing key surfaces as an explicit startup failure.
        """
        if not self.local_offline:
            return self

        switched: list[str] = []

        # 1) Embeddings: if configured for openai with a missing or placeholder
        #    key, fall back to the offline LocalEmbeddings provider.
        if self.embedding_provider == "openai" and self._is_placeholder_key(self.openai_api_key):
            self.embedding_provider = "local"
            switched.append("embedding_provider=local")

        # 2) Agents: for each (image, rule, verdict, chat) agent, if the
        #    currently configured provider has a missing or placeholder
        #    key, switch that agent to the offline LocalChatModel.
        for provider_field, _model_field in _AGENT_FIELDS:
            current_provider: str = getattr(self, provider_field)
            if current_provider == "local":
                continue
            api_key_field = _PROVIDER_API_KEY_FIELD.get(current_provider)
            if api_key_field is None:
                # Unknown provider — let the dependency factory surface the
                # error at first use rather than guessing here.
                continue
            api_key_value = getattr(self, api_key_field)
            if self._is_placeholder_key(api_key_value):
                setattr(self, provider_field, "local")
                switched.append(f"{provider_field}=local")

        if switched:
            logger.info(
                "local_provider_auto_defaults_applied",
                local_offline=self.local_offline,
                switched=switched,
            )
        return self

    @staticmethod
    def _is_placeholder_key(api_key: SecretStr | None) -> bool:
        """Return True if the supplied key is missing or is a known placeholder.

        Used by :meth:`validate_local_provider_defaults` to decide whether
        a configured provider should be auto-switched to ``local``.
        """
        if api_key is None:
            return True
        try:
            value = api_key.get_secret_value()
        except Exception:
            return True
        if value is None:
            return True
        stripped = value.strip()
        if not stripped:
            return True
        return stripped in _PLACEHOLDER_API_KEY_VALUES


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance. Cache is per-process (Lambda warm start safe)."""
    return Settings()
