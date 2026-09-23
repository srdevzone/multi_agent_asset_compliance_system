# ruff: noqa: N803, N818
"""
Local offline mock clients to emulate AWS S3, AWS DynamoDB, Pinecone, and
local-only embedding and chat model providers.

Allows full local development and testing without any AWS, Pinecone, or third-party
LLM credentials. Uses a SQLite backend for DynamoDB and Pinecone emulations,
the local filesystem under `.local_storage/s3/` for S3 emulation, and
deterministic zero-vector / canned-text responses for the offline embedding and
chat model providers.

Public classes in this module:

- :class:`LocalS3Client` — boto3-compatible S3 emulation (put/get/delete/paginate)
- :class:`LocalDynamoDBClient` — boto3-compatible DynamoDB emulation
- :class:`LocalPineconeIndex` — Pinecone Index emulation backed by Qdrant
- :class:`LocalEmbeddings` — offline embeddings provider returning zero-vectors
- :class:`LocalChatModel` — offline chat model returning canned responses
- :class:`LocalPaginator` — boto3-compatible paginator for ``list_objects_v2``
"""

import hashlib
import io
import sqlite3
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError
from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

# Maximum supported embedding vector dimension. Chosen to comfortably cover
# the largest models in current production use (OpenAI text-embedding-3-large
# exposes 3072 dimensions; we add generous headroom).
_MAX_EMBEDDING_DIMENSIONS: int = 8192
_MIN_EMBEDDING_DIMENSIONS: int = 1

# Canned text returned by LocalChatModel for every prompt. The text is
# deliberately stable and informative so downstream parsers that expect
# non-empty image descriptions do not crash during local development.
_LOCAL_CHAT_CANNED_TEXT: str = (
    "Local development placeholder: document described as compliance asset documentation."
)

# Single-page paginator contract — the offline emulation never truncates.
_LOCAL_PAGINATOR_MAX_KEYS: int = 1000

# ── S3 Mock Client ────────────────────────────────────────────────────────────


class LocalS3Client:
    """Offline emulation of the boto3 S3 client using the local filesystem.

    Exposes the subset of the boto3 S3 client surface used by the application:
    ``put_object``, ``get_object``, ``generate_presigned_url``,
    ``get_paginator``, and ``delete_objects``. The :meth:`get_object` method
    raises :class:`botocore.exceptions.ClientError` with ``Code="NoSuchKey"``
    when the requested key is missing, matching real boto3 semantics so the
    ``@s3_call`` resilience decorator behaves identically against this client.
    """

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def put_object(self, Bucket: str, Key: str, Body: Any) -> dict[str, Any]:
        """Write object bytes to a local file.

        ``Body`` may be raw ``bytes``, a file-like object exposing ``.read()``,
        or any object that can be ``str()``-coerced to UTF-8 text.
        """
        file_path = self.storage_dir / Bucket / Key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(Body, bytes):
            data = Body
        elif hasattr(Body, "read"):
            data = Body.read()
        else:
            data = str(Body).encode("utf-8")
        file_path.write_bytes(data)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        """Read object bytes from a local file.

        Raises:
            ClientError: with ``Code="NoSuchKey"`` when the file does not exist.
                This mirrors real boto3 behavior so the ``@s3_call`` retry layer
                treats the offline client identically to the real one.
        """
        file_path = self.storage_dir / Bucket / Key
        if not file_path.is_file():
            raise ClientError(
                error_response={
                    "Error": {
                        "Code": "NoSuchKey",
                        "Message": f"The specified key '{Key}' does not exist in bucket '{Bucket}'.",
                    }
                },
                operation_name="GetObject",
            )
        data = file_path.read_bytes()
        return {"Body": io.BytesIO(data), "ResponseMetadata": {"HTTPStatusCode": 200}}

    def generate_presigned_url(
        self, ClientMethod: str, Params: dict[str, Any], ExpiresIn: int = 3600
    ) -> str:
        """Return a local file URI representing the presigned URL.

        The ``ExpiresIn`` argument is accepted for signature parity with boto3
        but is not enforced — the returned URI is always usable while the file
        exists on disk.
        """
        bucket = str(Params.get("Bucket", ""))
        key = str(Params.get("Key", ""))
        file_path = (self.storage_dir / bucket / key).resolve()
        return file_path.as_uri()

    def get_paginator(self, paginator_name: str) -> "LocalPaginator":
        """Return a paginator for the given operation name.

        Args:
            paginator_name: Must be ``"list_objects_v2"``. Any other value
                raises :class:`ValueError` to surface caller mistakes early.

        Returns:
            LocalPaginator bound to this client's ``storage_dir``.

        Raises:
            ValueError: If ``paginator_name`` is not a supported paginator.
        """
        if paginator_name != "list_objects_v2":
            raise ValueError(
                f"Unsupported paginator: {paginator_name!r}. "
                "Only 'list_objects_v2' is supported by LocalS3Client."
            )
        return LocalPaginator(self.storage_dir)

    def delete_objects(
        self,
        Bucket: str,
        Delete: dict[str, Any],
    ) -> dict[str, Any]:
        """Delete the listed objects from the local bucket directory.

        Mirrors the boto3 ``delete_objects`` response shape exactly: the
        ``Deleted`` list always contains the keys that were requested, the
        ``Errors`` list is always empty, and the response carries an HTTP
        status code of 200. Missing keys are silently skipped — they are
        reported as deleted (matching boto3 semantics for absent keys when
        ``Quiet=False``).

        Args:
            Bucket: Bucket name (maps to a subdirectory under ``storage_dir``).
            Delete: Mapping of the form
                ``{"Objects": [{"Key": "<key>"}, ...], "Quiet": bool}``.

        Returns:
            Dictionary matching the boto3 response schema.
        """
        objects: list[dict[str, Any]] = Delete.get("Objects", [])
        deleted: list[dict[str, Any]] = []
        for obj in objects:
            key = obj["Key"]
            file_path = self.storage_dir / Bucket / key
            if file_path.is_file():
                file_path.unlink()
            deleted.append({"Key": key})
        return {
            "Deleted": deleted,
            "Errors": [],
            "ResponseMetadata": {"HTTPStatusCode": 200},
        }


# ── S3 Paginator ──────────────────────────────────────────────────────────────


class LocalPaginator:
    """Offline emulation of the boto3 ``list_objects_v2`` paginator.

    Walks ``storage_dir / Bucket / Prefix`` recursively and yields a single
    page of object metadata. The page shape matches boto3's
    ``list_objects_v2`` response so that callers (for example,
    :func:`app.services.s3_service.delete_asset_documents`) work unchanged
    against this client.
    """

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = Path(storage_dir)

    def paginate(
        self,
        Bucket: str,
        Prefix: str = "",
        PaginationConfig: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield a single page of object metadata for the given bucket/prefix.

        Args:
            Bucket: Bucket name (maps to a subdirectory under ``storage_dir``).
            Prefix: Key prefix to filter by. Empty string lists the entire
                bucket.
            PaginationConfig: Optional boto3 pagination configuration. Accepted
                for signature parity with boto3; ``MaxKeys`` and
                ``StartingToken`` are not enforced because the local backend
                returns a single page.

        Yields:
            A single dictionary with ``Contents``, ``IsTruncated``, ``Name``,
            ``Prefix``, and ``MaxKeys`` keys. When the bucket or prefix does
            not exist, the page contains an empty ``Contents`` list.

        Notes:
            ``PaginationConfig`` is intentionally accepted and ignored — local
            storage is fast enough that multi-page pagination is unnecessary
            and would complicate the on-disk format.
        """
        del PaginationConfig  # unused: local storage does not need paging
        base_path = self.storage_dir / Bucket / Prefix
        empty_page: dict[str, Any] = {
            "Contents": [],
            "IsTruncated": False,
            "Name": Bucket,
            "Prefix": Prefix,
            "MaxKeys": _LOCAL_PAGINATOR_MAX_KEYS,
        }
        if not base_path.is_dir():
            yield empty_page
            return

        contents: list[dict[str, Any]] = []
        bucket_root = self.storage_dir / Bucket
        for file_path in base_path.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                relative_key = str(file_path.relative_to(bucket_root))
            except ValueError:
                # Defensive: if the file escapes the bucket root for any reason
                # we skip it instead of leaking out-of-tree paths to callers.
                continue
            stat_result = file_path.stat()
            contents.append(
                {
                    "Key": relative_key,
                    "Size": stat_result.st_size,
                    "LastModified": datetime.fromtimestamp(stat_result.st_mtime, tz=UTC),
                    "ETag": hashlib.md5(file_path.read_bytes()).hexdigest(),  # noqa: S324
                }
            )

        yield {
            "Contents": contents,
            "IsTruncated": False,
            "Name": Bucket,
            "Prefix": Prefix,
            "MaxKeys": _LOCAL_PAGINATOR_MAX_KEYS,
        }


# ── Offline Embeddings Provider ──────────────────────────────────────────────


class LocalEmbeddings(Embeddings):
    """Deterministic offline embeddings provider.

    Returns zero-vectors of the configured dimension for every input. This
    satisfies the :class:`langchain_core.embeddings.Embeddings` interface so it
    can be substituted for any real provider (OpenAI, Anthropic, etc.) when
    running in fully-offline local development. Retrieval quality is, of
    course, degenerate because all vectors are identical — this class exists
    only to let the ingestion pipeline run end-to-end without network access.

    Invariant:
        Identical input always produces identical output (all zeros).
    """

    def __init__(self, dimensions: int) -> None:
        """Initialise the offline embeddings provider.

        Args:
            dimensions: Vector dimension count. Must match
                ``Settings.embedding_dimensions`` so the produced vectors
                are compatible with the configured Pinecone index.

        Raises:
            ValueError: If ``dimensions`` is outside the supported range
                ``[1, 8192]``.
        """
        if not isinstance(dimensions, int):
            raise TypeError(f"dimensions must be an int, got {type(dimensions).__name__}")
        if dimensions < _MIN_EMBEDDING_DIMENSIONS or dimensions > _MAX_EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"embedding_dimensions must be between "
                f"{_MIN_EMBEDDING_DIMENSIONS} and {_MAX_EMBEDDING_DIMENSIONS}, "
                f"got {dimensions}"
            )
        self.dimensions: int = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return a zero-vector for each input text.

        Args:
            texts: List of input strings. Not inspected — outputs are
                deterministic regardless of content.

        Returns:
            List of zero-vectors, one per input. Each inner list has length
            ``self.dimensions``.

        Contract:
            - ``len(result) == len(texts)``
            - ``len(result[i]) == self.dimensions`` for all ``i``
            - ``result[i][j] == 0.0`` for all ``i, j``
        """
        zero_vector: list[float] = [0.0] * self.dimensions
        return [list(zero_vector) for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        """Return a single zero-vector of length ``self.dimensions``.

        Args:
            text: Query string. Not inspected.

        Returns:
            Zero-vector with length ``self.dimensions``.
        """
        return [0.0] * self.dimensions

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Async variant of :meth:`embed_documents`.

        Delegates to the synchronous implementation. No async I/O is
        performed because the offline provider has no remote dependencies.
        """
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        """Async variant of :meth:`embed_query`.

        Delegates to the synchronous implementation. No async I/O is
        performed.
        """
        return self.embed_query(text)


# ── Offline Chat Model Provider ──────────────────────────────────────────────


class LocalChatModel(BaseChatModel):
    """Offline LLM provider returning canned responses.

    Satisfies :class:`langchain_core.language_models.chat_models.BaseChatModel`
    so it can be used anywhere a chat model is required (image description
    in the image agent, rule/verdict/chat agent invocations during local
    development). Every invocation returns a deterministic
    :class:`AIMessage` whose content is :data:`_LOCAL_CHAT_CANNED_TEXT`,
    regardless of the input prompt.

    Invariant:
        :meth:`_generate` MUST NOT raise under any input and MUST NOT
        perform network I/O. This is required so the agent nodes that
        consume this model degrade gracefully in fully-offline mode.
    """

    # Pydantic model fields required by BaseChatModel's serialisation
    # machinery. ``model_name`` is exposed as the canonical model identifier
    # in logs and traces; ``temperature`` is a no-op for the canned provider.
    model_name: str = "local-dummy"
    temperature: float = 0.0

    @property
    def _llm_type(self) -> str:
        """Return the provider discriminator used by LangChain internals."""
        return "local_dummy"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """Return the model parameters that uniquely identify this instance."""
        return {"model_name": self.model_name, "temperature": self.temperature}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Return a canned :class:`ChatResult` for any input.

        The ``messages``, ``stop``, ``run_manager``, and ``kwargs`` arguments
        are intentionally accepted but unused: the offline provider always
        produces the same deterministic output.

        Args:
            messages: Prompt messages (ignored).
            stop: Optional stop sequences (ignored).
            run_manager: Optional callback manager (ignored).
            **kwargs: Additional keyword arguments (ignored).

        Returns:
            :class:`ChatResult` containing a single :class:`ChatGeneration`
            whose :class:`AIMessage` carries the canned description.
        """
        del messages, stop, run_manager, kwargs
        message = AIMessage(content=_LOCAL_CHAT_CANNED_TEXT)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async variant of :meth:`_generate`.

        Delegates to the synchronous implementation. No async I/O is
        performed.
        """
        del run_manager  # unused: sync call requires no async callback wiring
        return self._generate(messages, stop=stop, **kwargs)


# ── DynamoDB Mock Client ──────────────────────────────────────────────────────


class ConditionalCheckFailedException(Exception):
    """Exception raised when a DynamoDB put_item condition check fails."""

    pass


class LocalDynamoDBExceptions:
    """Wrapper class to emulate boto3's client exceptions namespace."""

    ConditionalCheckFailedException = ConditionalCheckFailedException


class LocalDynamoDBClient:
    """Offline emulation of the boto3 DynamoDB client using a SQLite database."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.exceptions = LocalDynamoDBExceptions
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database structure for audit run tracking."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_runs (
                    run_id TEXT PRIMARY KEY,
                    asset_id TEXT,
                    status TEXT,
                    verdict TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    expires_at INTEGER,
                    error_message TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_runs_asset_id ON audit_runs(asset_id)"
            )

    def put_item(
        self, TableName: str, Item: dict[str, Any], ConditionExpression: str | None = None
    ) -> dict[str, Any]:
        """Insert or replace an audit run item, checking for unique run_id if requested."""
        run_id = Item["run_id"]["S"]
        asset_id = Item["asset_id"]["S"]
        status = Item["status"]["S"]
        created_at = Item["created_at"]["S"]
        updated_at = Item["updated_at"]["S"]
        expires_at = int(Item["expires_at"]["N"])

        with sqlite3.connect(self.db_path) as conn:
            if ConditionExpression and "attribute_not_exists" in ConditionExpression:
                cursor = conn.execute("SELECT 1 FROM audit_runs WHERE run_id = ?", (run_id,))
                if cursor.fetchone():
                    raise ConditionalCheckFailedException(
                        f"ConditionalCheckFailed: Item with run_id '{run_id}' already exists."
                    )

            conn.execute(
                """
                INSERT OR REPLACE INTO audit_runs (run_id, asset_id, status, created_at, updated_at, expires_at, verdict, error_message)
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (run_id, asset_id, status, created_at, updated_at, expires_at),
            )
        return {}

    def get_item(
        self, TableName: str, Key: dict[str, Any], ConsistentRead: bool = False
    ) -> dict[str, Any]:
        """Fetch an audit run item by run_id."""
        run_id = Key["run_id"]["S"]
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM audit_runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()

        if not row:
            return {}

        item: dict[str, Any] = {
            "run_id": {"S": row["run_id"]},
            "asset_id": {"S": row["asset_id"]},
            "status": {"S": row["status"]},
            "created_at": {"S": row["created_at"]},
            "updated_at": {"S": row["updated_at"]},
            "expires_at": {"N": str(row["expires_at"])},
        }
        if row["verdict"] is not None:
            item["verdict"] = {"S": row["verdict"]}
        if row["error_message"] is not None:
            item["error_message"] = {"S": row["error_message"]}

        return {"Item": item}

    def update_item(
        self,
        TableName: str,
        Key: dict[str, Any],
        UpdateExpression: str,
        ExpressionAttributeNames: dict[str, str] | None = None,
        ExpressionAttributeValues: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update fields on an existing audit run item."""
        run_id = Key["run_id"]["S"]

        status: str | None = None
        verdict: str | None = None
        error_message: str | None = None
        updated_at: str | None = None

        if ExpressionAttributeValues:
            if ":s" in ExpressionAttributeValues:
                status = ExpressionAttributeValues[":s"]["S"]
            if ":v" in ExpressionAttributeValues:
                verdict = ExpressionAttributeValues[":v"]["S"]
            if ":e" in ExpressionAttributeValues:
                error_message = ExpressionAttributeValues[":e"]["S"]
            if ":u" in ExpressionAttributeValues:
                updated_at = ExpressionAttributeValues[":u"]["S"]

        updates = []
        params: list[Any] = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if verdict is not None:
            updates.append("verdict = ?")
            params.append(verdict)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if updated_at is not None:
            updates.append("updated_at = ?")
            params.append(updated_at)

        if not updates:
            return {}

        params.append(run_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE audit_runs SET {', '.join(updates)} WHERE run_id = ?",  # noqa: S608
                params,
            )
        return {}

    def query(
        self,
        TableName: str,
        IndexName: str | None = None,
        KeyConditionExpression: str | None = None,
        ExpressionAttributeValues: dict[str, Any] | None = None,
        ProjectionExpression: str | None = None,
        ExpressionAttributeNames: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Query audit runs by asset_id using the emulated AssetIdIndex GSI."""
        asset_id = ""
        if ExpressionAttributeValues and ":aid" in ExpressionAttributeValues:
            asset_id = ExpressionAttributeValues[":aid"]["S"]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM audit_runs WHERE asset_id = ?", (asset_id,))
            rows = cursor.fetchall()

        items = []
        for row in rows:
            item: dict[str, Any] = {
                "run_id": {"S": row["run_id"]},
                "asset_id": {"S": row["asset_id"]},
                "status": {"S": row["status"]},
                "created_at": {"S": row["created_at"]},
                "updated_at": {"S": row["updated_at"]},
                "expires_at": {"N": str(row["expires_at"])},
            }
            if row["verdict"] is not None:
                item["verdict"] = {"S": row["verdict"]}
            if row["error_message"] is not None:
                item["error_message"] = {"S": row["error_message"]}
            items.append(item)

        return {"Items": items}


# ── Pinecone Mock Client ──────────────────────────────────────────────────────


class NamespaceStats:
    """Simulates a namespace statistics object returned by describe_index_stats."""

    def __init__(self, vector_count: int) -> None:
        self.vector_count = vector_count


class IndexStats:
    """Simulates the index statistics returned by describe_index_stats."""

    def __init__(self, namespaces: dict[str, NamespaceStats], dimension: int = 1536) -> None:
        self.namespaces = namespaces
        self.dimension = dimension


class PineconeMatch:
    """Simulates a single query match returned by the Pinecone index query."""

    def __init__(self, id: str, score: float, metadata: dict[str, Any] | None = None) -> None:
        self.id = id
        self.score = score
        self.metadata = metadata


class QueryResponse:
    """Simulates the query response containing a list of matches."""

    def __init__(self, matches: list[PineconeMatch]) -> None:
        self.matches = matches


class LocalPineconeIndex:
    """Offline emulation of the Pinecone Index client using Qdrant client."""

    def __init__(self, db_path: Path, embedding_dimensions: int) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_dimensions = embedding_dimensions
        self.client = QdrantClient(path=str(self.db_path))

    def upsert(self, vectors: list[dict[str, Any]], namespace: str) -> dict[str, Any]:
        """Upsert a list of vectors with their metadata into the Qdrant collection."""
        if not self.client.collection_exists(collection_name=namespace):
            self.client.create_collection(
                collection_name=namespace,
                vectors_config=VectorParams(
                    size=self.embedding_dimensions, distance=Distance.COSINE
                ),
            )

        points = []
        for vec in vectors:
            vec_id = vec["id"]
            values = vec["values"]
            metadata = vec.get("metadata", {})

            # Convert custom string ID to valid Qdrant UUID
            hashed_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, vec_id))
            payload = {"_original_id": vec_id, **metadata}

            points.append(
                PointStruct(
                    id=hashed_id,
                    vector=values,
                    payload=payload,
                )
            )

        self.client.upsert(collection_name=namespace, points=points)
        return {"upserted_count": len(vectors)}

    def delete(
        self,
        ids: list[str] | None = None,
        delete_all: bool | None = None,
        namespace: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Delete vectors by ID, namespace, or metadata filters."""
        if not namespace or not self.client.collection_exists(collection_name=namespace):
            return {}

        if delete_all:
            self.client.delete_collection(collection_name=namespace)
        elif ids:
            hashed_ids: list[Any] = [str(uuid.uuid5(uuid.NAMESPACE_DNS, val)) for val in ids]
            self.client.delete(
                collection_name=namespace,
                points_selector=PointIdsList(points=hashed_ids),
            )
        elif filter:
            qdrant_filter = self._translate_filter(filter)
            if qdrant_filter:
                self.client.delete(
                    collection_name=namespace,
                    points_selector=FilterSelector(filter=qdrant_filter),
                )
        return {}

    def query(
        self,
        vector: list[float],
        top_k: int,
        namespace: str,
        include_metadata: bool = False,
        filter: dict[str, Any] | None = None,
    ) -> QueryResponse:
        """Query vectors within a namespace, applying filters and retrieving from Qdrant."""
        if not self.client.collection_exists(collection_name=namespace):
            return QueryResponse(matches=[])

        qdrant_filter = self._translate_filter(filter)
        search_results = self.client.query_points(
            collection_name=namespace,
            query=vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )

        matches = []
        for hit in search_results.points:
            payload = hit.payload or {}
            original_id = payload.get("_original_id")
            original_id_str = str(original_id) if original_id is not None else str(hit.id)

            metadata = {}
            if include_metadata:
                metadata = {k: v for k, v in payload.items() if k != "_original_id"}

            matches.append(
                PineconeMatch(
                    id=original_id_str,
                    score=float(hit.score),
                    metadata=metadata,
                )
            )
        return QueryResponse(matches=matches)

    def list(
        self, prefix: str | None = None, namespace: str | None = None, limit: int = 100
    ) -> Any:
        """Simulate Pinecone's list method, returning a generator of ID lists."""
        if not namespace or not self.client.collection_exists(collection_name=namespace):
            return

        offset = None
        while True:
            records, next_offset = self.client.scroll(
                collection_name=namespace,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            if not records:
                break

            ids_batch = []
            for r in records:
                payload = r.payload or {}
                orig_id = str(payload.get("_original_id", r.id))
                if prefix is None or orig_id.startswith(prefix):
                    ids_batch.append(orig_id)

            if ids_batch:
                yield ids_batch

            if next_offset is None:
                break
            offset = next_offset

    def describe_index_stats(self) -> IndexStats:
        """Return counts of vectors grouped by namespace (collection)."""
        collections_resp = self.client.get_collections()
        namespaces = {}
        for col in collections_resp.collections:
            col_info = self.client.get_collection(collection_name=col.name)
            namespaces[col.name] = NamespaceStats(vector_count=col_info.points_count or 0)
        return IndexStats(namespaces=namespaces, dimension=self.embedding_dimensions)

    def _translate_filter(self, pinecone_filter: dict[str, Any] | None) -> Filter | None:
        """Translate a Pinecone filter dict into a Qdrant Filter object."""
        if not pinecone_filter:
            return None

        must_conditions: list[Any] = []
        for key, cond in pinecone_filter.items():
            if isinstance(cond, dict) and "$eq" in cond:
                val = cond["$eq"]
            else:
                val = cond

            must_conditions.append(
                FieldCondition(
                    key=key,
                    match=MatchValue(value=val),
                )
            )
        return Filter(must=must_conditions)
