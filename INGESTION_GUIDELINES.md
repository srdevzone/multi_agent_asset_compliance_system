# Enterprise Document Ingestion & Embedding Guidelines

This guide details how to prepare, structure, and execute asset documentation ingestion for the **Asset Compliance AI** microservice. Following these guidelines ensures high retrieval accuracy (RAG) during compliance auditing.

> **What's new in this revision**
>
> - **Direct Upload Endpoint** (`POST /api/v1/ingest/upload`) — a multipart
>   upload path that accepts files inline, writes them to S3, and runs the
>   full ingest pipeline in one call. This complements the existing JSON
>   endpoint which assumes files are already in S3.
> - **Local / Offline Development Mode** — zero-API-key development
>   against local emulations of S3, DynamoDB, and Pinecone.
> - **OpenCode Zen & Go gateway support** — additional LLM provider
>   options for cost-effective agent routing.
> - **Stricter input validation** — `asset_id` is now regex-checked
>   *before* any request body bytes are read.

---

## 1. Supported Document Types & Formats

The ingestion pipeline accepts two kinds of source:

1. **Files already in your enterprise Amazon S3 bucket** — referenced
   by their S3 key via the `POST /api/v1/ingest` JSON endpoint.
2. **Files uploaded directly from a client** (browser, mobile,
   integration) — sent as `multipart/form-data` via the
   `POST /api/v1/ingest/upload` endpoint, which writes them to S3
   internally before running the same ingest pipeline.

### Document Classifications (`doc_type`)
When registering a file, you must assign one of the following classification tags:
* `user_manual`: Equipment operating manuals, technical reference booklets, and manufacturer instructions.
* `safety_sheet`: Material Safety Data Sheets (MSDS), hazard notices, and safety guidelines.
* `compliance_spec`: Site rules, government regulations, or corporate compliance standards.
* `installation_image`: On-site photographs showing the physical installation of the asset.
* `other`: Any auxiliary document that doesn't fit the above but contains context for auditing.

### File Format Requirements
| File Type | Supported Formats | Processing Method | Preparation Guidelines |
| :--- | :--- | :--- | :--- |
| **Documents** | PDF (`.pdf`) | Text extracted page-by-page with `pypdf`; by default, small searchable child chunks retain larger parent context. | **Must contain text layers.** If you have scanned physical paper, run **OCR (Optical Character Recognition)** before uploading. Passwords or encryption must be removed. |
| **Images** | JPEG (`.jpg`, `.jpeg`), PNG (`.png`), WebP (`.webp`) | Transmitted as Base64 to a **Vision LLM** to produce a dense text description, which is then embedded as a single vector. | Use high-resolution images. Ensure labels, barcodes, rating plates, or warning stickers are legible, well-lit, and un-obscured. |

### How `doc_type` is inferred on the direct-upload endpoint

When you upload a file via `/api/v1/ingest/upload`, the service infers
`doc_type` from the filename extension and a small set of filename
keywords so callers do not need to supply it explicitly. The rules are:

| Extension | Inferred `doc_type` |
| :--- | :--- |
| `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif` | `installation_image` |
| `.pdf` containing `manual` or `user` in its name | `user_manual` |
| `.pdf` containing `safety` or `msds` in its name | `safety_sheet` |
| `.pdf` (other) | `compliance_spec` |
| anything else | `other` |

The JSON endpoint still requires you to supply `doc_type` explicitly per
document, since the server has no file to inspect.

---

## 2. Ingestion Lifecycles & Batching

The service exposes two ingest endpoints, each with its own lifecycle
model. Pick the one that matches how your files arrive.

### 2.1 JSON ingest (files already in S3)

`POST /api/v1/ingest` supports three lifecycle events:

1. **`create` (Initial Asset Registration):**
   * Use this when registering an asset for the first time.
   * **Idempotency Guard:** If the asset's Pinecone namespace already has vectors, the system will skip reprocessing to prevent redundant cost and API usage.
   * **Batching:** You can send a list of up to 50 documents in a single request.
2. **`add` (Append Documentation):**
   * Use this to add new manuals, specifications, or images to an asset that has already been registered.
   * New document chunks are embedded and appended to the existing namespace.
3. **`update` (Surgical Replacement):**
   * Use this to update a specific document (e.g., uploading a newer version of a manual).
   * **Exactly one document** must be sent in the request list.
   * The pipeline automatically locates and deletes all old vector chunks matching the `doc_id` inside the namespace, then embeds and writes the new file.

### 2.2 Direct upload (files uploaded inline)

`POST /api/v1/ingest/upload` accepts files as `multipart/form-data` and
runs the same downstream pipeline. The two supported events are:

1. **`create`** — same semantics as the JSON endpoint. The service
   writes the file to S3 under `<asset_id>/<sanitized-filename>`, infers
   the `doc_type`, then runs the same chunk → embed → upsert flow.
   * **Idempotency Guard:** Skipped if the namespace already has
     vectors.
2. **`add`** — appends the uploaded files to an existing namespace. No
   `update` event is supported on the upload endpoint (surgical
   replacement requires a known `doc_id` from the JSON endpoint).

The upload endpoint is **not** a replacement for the JSON endpoint; it
is a convenience for callers that do not already have an S3 staging
bucket or a Django/enterprise backend writing to S3. For example, a
field technician uploading a photograph from a phone browser uses the
upload endpoint. A nightly batch job that already writes PDFs to a
known S3 prefix uses the JSON endpoint.

### 2.3 GDPR Erasure (Right-to-Erasure)

* To completely wipe an asset's records from the system, do not use the
  ingest endpoints.
* Instead, call `DELETE /api/v1/admin/assets/{asset_id}`. This purges
  Pinecone vectors, S3 documents, S3 images, and DynamoDB logs.
* The erasure endpoint paginates S3 with `list_objects_v2` and calls
  `delete_objects` — both operations are supported by the production
  boto3 client **and** by the local emulated client used in offline
  development, so the same code path is exercised in both modes.

### Idempotency of Pinecone Upserts

When the same PDF is ingested twice, the system handles it as follows:

**`create` Event** (JSON or upload):
- If the asset namespace already has vectors, the ingestion is
  **skipped entirely** (idempotency guard).
- No duplicate vectors are created, and no additional embedding API
  calls are made.

**`add` Event** (JSON or upload):
- **Duplicate vectors will be created** if the same `doc_id` is
  ingested again.
- This is by design — `add` is meant for appending new documents, not
  re-ingesting existing ones.
- **Mitigation**: Use the `update` event instead if you need to
  re-ingest a document (JSON endpoint only).

**`update` Event** (JSON only):
- **Fully idempotent**: Old vectors for the `doc_id` are deleted, then
  new vectors are written.
- Re-ingesting the same document with the same `doc_id` will replace
  the existing vectors with identical ones.
- No duplicate vectors accumulate in the namespace.

**Best Practices**:
- Always use stable `doc_id` values from your backend database.
- Use `update` when re-ingesting the same document to avoid duplicates.
- For `add` operations, ensure the `doc_id` is unique before appending.
- Monitor vector counts via the Pinecone console to detect accidental duplicates.

---

## 3. Preparing Files for Ingestion (Enterprise Best Practices)

To maximize RAG retrieval efficiency and compliance audit accuracy:
* **Strict S3 Key Formatting:** To prevent directory traversal attacks, `s3_key` values must strictly adhere to the regex `^[a-zA-Z0-9/_\-\.]+$`. Do not use spaces or special characters in filenames or paths.
* **Stable Document IDs (`doc_id`):** Your main database (e.g., backend client) must assign and maintain stable, unique identifiers for documents. When replacing a manual, keep the same `doc_id` and send it with the `update` lifecycle event.
* **Keep Documents Segmented:** Rather than merging all manuals into one giant PDF, upload them as separate S3 keys and register them as individual items. This ensures accurate source-attribution and file citations.
* **Avoid Non-Standard File Types:** Word documents (`.docx`), Excel files (`.xlsx`), or plain text (`.txt`) are not natively chunked. Convert text guidelines into PDFs before uploading to S3.
* **Filename Sanitization on the Upload Endpoint:** The upload endpoint
  strips any character that is not alphanumeric, a hyphen, an
  underscore, or a period, replacing it with `_` before constructing
  the S3 key. To keep `doc_id` values predictable, prefer ASCII-only
  filenames. The `doc_id` for a file uploaded as
  `pump_5000_user_guide.pdf` becomes `doc_pump_5000_user_guide`.

### Parent-document retrieval considerations

Parent-document retrieval is enabled by default (`PDR_ENABLED=true`). Child chunks are embedded for precise matching, while parent text is retained in metadata and included in downstream prompts. Changing `PDR_PARENT_CHUNK_SIZE`, `PDR_CHILD_CHUNK_SIZE`, or `PDR_CHILD_OVERLAP` affects only newly ingested documents. Re-ingest existing documents if they must use the new chunk layout or carry parent context.

Hybrid BM25/dense scoring and optional FlashRank reranking happen at query time; they do not require additional sparse vectors during ingestion. See [docs/RETRIEVAL_PIPELINE.md](docs/RETRIEVAL_PIPELINE.md).

---

## 4. How to Execute Ingestions (API Integration)

All requests must include the timing-safe shared API key in the headers.

### 4.1 JSON endpoint (files already in S3)

* **Method:** `POST`
* **Path:** `/api/v1/ingest`
* **Header:** `X-API-Key: <your-API_SECRET_KEY>`
* **Content-Type:** `application/json`

#### Example Request Body (Batch Ingest on Create)
```json
{
  "asset_id": "8a3d5e21-9654-4f2e-bf72-87adac23b102",
  "event": "create",
  "documents": [
    {
      "s3_key": "raw-uploads/pump_5000_user_guide.pdf",
      "doc_id": "doc-manual-5000",
      "doc_type": "user_manual",
      "filename": "pump_5000_user_guide.pdf"
    },
    {
      "s3_key": "raw-uploads/pump_5000_safety.pdf",
      "doc_id": "doc-safety-5000",
      "doc_type": "safety_sheet",
      "filename": "pump_5000_safety.pdf"
    },
    {
      "s3_key": "raw-uploads/pump_5000_installation_photo.png",
      "doc_id": "doc-photo-5000",
      "doc_type": "installation_image",
      "filename": "pump_5000_installation_photo.png"
    }
  ]
}
```

#### Python Integration Example (Backend/Enterprise Client)
```python
import requests
import json

COMPLIANCE_SERVICE_URL = "https://<your-lambda-url>.lambda-url.us-east-1.on.aws"
API_KEY = "your-shared-api-secret-key"

payload = {
    "asset_id": "8a3d5e21-9654-4f2e-bf72-87adac23b102",
    "event": "create",
    "documents": [
        {
            "s3_key": "assets/manuals/HP-5000.pdf",
            "doc_id": "manual-hp-5000-v1",
            "doc_type": "user_manual",
            "filename": "HP-5000_User_Manual.pdf"
        }
    ]
}

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

response = requests.post(
    f"{COMPLIANCE_SERVICE_URL}/api/v1/ingest",
    headers=headers,
    data=json.dumps(payload)
)

if response.status_code == 200:
    data = response.json()
    print(f"Success! Namespace: {data['namespace']}, Vectors Upserted: {data['vectors_upserted']}")
else:
    print(f"Failed: {response.status_code} - {response.text}")
```

### 4.2 Upload endpoint (files uploaded inline)

* **Method:** `POST`
* **Path:** `/api/v1/ingest/upload`
* **Header:** `X-API-Key: <your-API_SECRET_KEY>`
* **Content-Type:** `multipart/form-data`

#### Form fields

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `asset_id` | string | yes | Must match the regex `^[a-zA-Z0-9_-]+$`. Validated **before** any file bytes are read, so a bad `asset_id` returns `400` without consuming the request body. |
| `event` | string | yes | One of `create` or `add`. The `update` event is not supported on the upload endpoint. |
| `files` | file (one or more) | yes | The file(s) to upload. Allowed extensions: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`. The server infers `doc_type` from the extension and filename keywords. |

#### Response (same shape as the JSON endpoint)

```json
{
  "asset_id": "8a3d5e21-9654-4f2e-bf72-87adac23b102",
  "event": "create",
  "documents_processed": 2,
  "vectors_upserted": 14,
  "vectors_deleted": 0,
  "completed_at": "2026-07-13T12:34:56.789Z",
  "namespace": "asset_8a3d5e21-9654-4f2e-bf72-87adac23b102"
}
```

#### Validation and error handling

| Status | Meaning | When |
| :--- | :--- | :--- |
| `200 OK` | Ingest succeeded (or was skipped via the `create` idempotency guard). | Always for valid input. |
| `400 BAD_REQUEST` | `asset_id` failed the regex check, or no `files` were provided, or the `event` is not one of the allowed values. | Invalid input — the request body is **not** consumed when the regex check fails. |
| `401 UNAUTHORIZED` | The `X-API-Key` header is missing or does not match `API_SECRET_KEY`. | Every request. |
| `503 SERVICE_UNAVAILABLE` | `API_SECRET_KEY` is not configured on the server. | Missing configuration — see the deployment guide. |

The pipeline is resilient: if a single file fails to chunk or embed,
its vectors_upserted contribution is reported as `0` and the failure
is logged via `structlog`. The remaining files in the same batch
continue to process. Always check `vectors_upserted` against
`documents_processed` in the response.

#### Frontend example (browser)

```html
<form action="https://<your-lambda-url>.lambda-url.us-east-1.on.aws/api/v1/ingest/upload"
      method="post"
      enctype="multipart/form-data">
  <label>Asset ID
    <input type="text" name="asset_id" required pattern="[a-zA-Z0-9_-]+" />
  </label>
  <label>Lifecycle
    <select name="event" required>
      <option value="create">create (first ingest)</option>
      <option value="add">add (append)</option>
    </select>
  </label>
  <label>Documents
    <input type="file" name="files" accept=".pdf,.jpg,.jpeg,.png,.webp,.gif" multiple required />
  </label>
  <button type="submit">Upload</button>
</form>
```

#### Python example (`requests`)

```python
import requests

COMPLIANCE_SERVICE_URL = "https://<your-lambda-url>.lambda-url.us-east-1.on.aws"
API_KEY = "your-shared-api-secret-key"

with open("pump_5000_user_guide.pdf", "rb") as pdf, \
     open("pump_5000_safety.pdf", "rb") as msds:
    response = requests.post(
        f"{COMPLIANCE_SERVICE_URL}/api/v1/ingest/upload",
        headers={"X-API-Key": API_KEY},
        data={
            "asset_id": "8a3d5e21-9654-4f2e-bf72-87adac23b102",
            "event": "create",
        },
        files=[
            ("files", ("pump_5000_user_guide.pdf", pdf, "application/pdf")),
            ("files", ("pump_5000_safety.pdf", msds, "application/pdf")),
        ],
        timeout=120,
    )

response.raise_for_status()
body = response.json()
print(f"Namespace: {body['namespace']}")
print(f"Documents: {body['documents_processed']}")
print(f"Vectors:   {body['vectors_upserted']}")
```

#### `curl` example

```bash
curl -X POST \
  -H "X-API-Key: your-shared-api-secret-key" \
  -F "asset_id=8a3d5e21-9654-4f2e-bf72-87adac23b102" \
  -F "event=create" \
  -F "files=@pump_5000_user_guide.pdf" \
  -F "files=@pump_5000_safety.pdf" \
  https://<your-lambda-url>.lambda-url.us-east-1.on.aws/api/v1/ingest/upload
```

---

## 5. Local & Offline Development Mode

For developers running the service locally without AWS or Pinecone
credentials, set `LOCAL_OFFLINE=True` in your `.env`. The application
will:

- **S3** → route to `LocalS3Client` (filesystem under
  `.local_storage/s3/<bucket>/`).
- **DynamoDB** → route to `LocalDynamoDBClient` (SQLite at
  `.local_storage/dynamodb.db`).
- **Pinecone** → route to `LocalPineconeIndex` (Qdrant client backed
  by `.local_storage/qdrant/`).
- **Embeddings** → `LocalEmbeddings` (deterministic zero-vectors of
  the configured dimension) **OR** your configured remote provider,
  depending on `EMBEDDING_PROVIDER`.
- **LLMs** → `LocalChatModel` (canned response) **OR** your configured
  remote provider, depending on `*_AGENT_PROVIDER`.

### 5.1 Zero-config auto-switch

To make local development friction-free, the `Settings` validator
**auto-switches** any provider that has a missing or placeholder
API key to `local` when `LOCAL_OFFLINE=True`. The placeholder
values that trigger the auto-switch are:

```
sk-proj-xxx
sk-ant-xxx
sk-or-v1-...
your-pinecone-api-key
your-xai-grok-api-key
your-shared-secret-key-min-32-chars
your-langsmith-api-key
your-opencode-zen-api-key
your-opencode-go-api-key
```

In staging and production (`LOCAL_OFFLINE=False`) the auto-switch
**never runs** — any missing key surfaces as a normal startup
failure.

### 5.2 What works in offline mode

| Operation | Offline Support | Notes |
| :--- | :--- | :--- |
| JSON ingest (`POST /api/v1/ingest`) | ✅ | S3 read, embeddings, Pinecone upsert all work against the local emulations. |
| Direct upload (`POST /api/v1/ingest/upload`) | ✅ | File is written to `LocalS3Client` and processed identically. |
| GDPR erasure (`DELETE /api/v1/admin/assets/{id}`) | ✅ | `LocalS3Client.get_paginator` and `delete_objects` are full boto3-compatible. |
| Image description (vision LLM) | ⚠️ Returns canned text | `LocalChatModel._generate` always returns the same canned description. The downstream pipeline completes, but the description is not real. |
| Retrieval (audit / chat) | ⚠️ Zero-vector recall | All embeddings are zero-vectors so cosine similarity is undefined; the first matching vector in the namespace is returned. Do not rely on retrieval quality in offline mode — it is a wiring test only. |

### 5.3 Smoke test (offline)

```bash
echo "LOCAL_OFFLINE=True" > .env
echo "EMBEDDING_PROVIDER=local" >> .env
echo "IMAGE_AGENT_PROVIDER=local" >> .env
echo "RULE_AGENT_PROVIDER=local" >> .env
echo "VERDICT_AGENT_PROVIDER=local" >> .env
echo "CHAT_AGENT_PROVIDER=local" >> .env
echo "API_SECRET_KEY=local-dev-secret" >> .env

make local-api
# In another terminal, open http://localhost:8000 and upload a PDF via the UI.
# Verify the file lands under .local_storage/s3/<bucket>/<asset_id>/<file>.
```

---

## 6. LLM Provider Configuration

The four agent slots (`image`, `rule`, `verdict`, `chat`) and the
embedding slot can each be routed to a different provider. The
following providers are supported:

| Provider | Notes |
| :--- | :--- |
| `openai` | Native OpenAI; requires `OPENAI_API_KEY`. |
| `anthropic` | Native Anthropic; requires `ANTHROPIC_API_KEY`. |
| `google_genai` | Google Gemini; requires `GOOGLE_API_KEY`. |
| `xai` / `grok` | xAI Grok; requires `XAI_API_KEY`. |
| `openrouter` | OpenRouter gateway; requires `OPENROUTER_API_KEY`. Base URL: `https://openrouter.ai/api/v1`. |
| `zen` | **OpenCode Zen** pay-as-you-go gateway; requires `ZEN_API_KEY`. Base URL: `https://opencode.ai/zen/v1`. |
| `opencode_go` | **OpenCode Go** subscription gateway; requires `OPENCODE_GO_API_KEY`. Base URL: `https://opencode.ai/zen/go/v1`. |
| `local` | Offline canned-response provider; no API key required. Only used in `LOCAL_OFFLINE=True`. |

### 6.1 OpenCode Zen & Go — important caveats

- **Base URLs are pinned at compile time.** They are **not**
  configurable via environment variables. This is intentional: an
  env-configurable base URL would create an SSRF surface that lets an
  operator (or a leaked env var) redirect your traffic to an
  attacker-controlled endpoint.
- **Embeddings are not provided.** OpenCode Zen and Go are
  chat-completion-only. If you route agents through Zen/Go, you must
  also set `EMBEDDING_PROVIDER` to a real embeddings backend (typically
  `openai` with `text-embedding-3-small`).
- **Recommended model pairings** — these are the models most
  commonly used for each agent slot:
  - **Image agent** (vision required): Zen → `gpt-5.4` or
    `claude-sonnet-4.6`; Go → `qwen3.7-max`.
  - **Rule agent** (reasoning): Zen/Go → `qwen3.6-plus`.
  - **Verdict agent** (complex analysis): Zen/Go → `qwen3.7-plus`.
  - **Chat agent** (conversational): Zen/Go → `qwen3.6-plus`.

### 6.2 Example: route all four agents through OpenCode Zen

```bash
# .env
ZEN_API_KEY=zen-xxxxxxxxxxxxxxxxxxxx
IMAGE_AGENT_PROVIDER=zen
IMAGE_AGENT_MODEL=gpt-5.4
RULE_AGENT_PROVIDER=zen
RULE_AGENT_MODEL=qwen3.6-plus
VERDICT_AGENT_PROVIDER=zen
VERDICT_AGENT_MODEL=qwen3.7-plus
CHAT_AGENT_PROVIDER=zen
CHAT_AGENT_MODEL=qwen3.6-plus

# OpenAI is still required for embeddings.
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

### 6.3 Example: route agents through OpenCode Go (subscription)

```bash
# .env
OPENCODE_GO_API_KEY=go-xxxxxxxxxxxxxxxxxxxx
IMAGE_AGENT_PROVIDER=opencode_go
IMAGE_AGENT_MODEL=qwen3.7-max
RULE_AGENT_PROVIDER=opencode_go
RULE_AGENT_MODEL=qwen3.6-plus
VERDICT_AGENT_PROVIDER=opencode_go
VERDICT_AGENT_MODEL=qwen3.7-plus
CHAT_AGENT_PROVIDER=opencode_go
CHAT_AGENT_MODEL=qwen3.6-plus

OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

---

## 7. Quick Reference

| Task | Endpoint | Method |
| :--- | :--- | :--- |
| Register a new asset (files already in S3) | `/api/v1/ingest` | `POST` JSON |
| Append a new document to an existing asset | `/api/v1/ingest` | `POST` JSON, `event: "add"` |
| Replace one document surgically | `/api/v1/ingest` | `POST` JSON, `event: "update"` |
| Upload files inline from a browser or script | `/api/v1/ingest/upload` | `POST` multipart |
| Erase all data for an asset (GDPR) | `/api/v1/admin/assets/{asset_id}` | `DELETE` |
| Inspect an asset's vector count and audit history | `/api/v1/admin/assets/{asset_id}/stats` | `GET` |
