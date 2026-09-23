# How It Works: The Asset Compliance AI Lifecycle

This document provides a detailed, step-by-step narrative of exactly how the Asset Compliance AI system operates under the hood, from the moment an asset is registered to the final automated compliance verdict.

---

## Step 1: Ingestion of Compliance Ground Truth

Before the AI can audit an asset, it needs to know what the rules are. 

1. **Upload:** A compliance manager uploads regulatory PDFs, user manuals, and safety sheets to the enterprise backend system. backend client saves these files to an AWS S3 bucket.
2. **API Call:** backend client calls our AI microservice endpoint `POST /api/v1/ingest`. It passes the `asset_id` and the `s3_key` where the file lives.
3. **Processing:**
   - The AI downloads the raw PDF bytes from S3.
   - It uses `pypdf` (via `document_loader.py`) to parse text from every PDF page.
   - By default, text is split into large parent chunks (2048 characters) and smaller overlapping child chunks (256 characters, 32 overlap).
4. **Vectorisation:** The AI embeds the small child chunks. Each child retains its parent text as metadata so retrieval can combine precise matching with broader context.
5. **Storage:** The child vectors and metadata are saved in the **Pinecone Vector Database** under a namespace named `asset_<ASSET_ID>`. This prevents documentation from different assets being mixed.

---

## Step 2: The Field Audit

An auditor travels to the physical location of the asset (e.g., a factory floor).

1. **Inspection:** The auditor takes photos of the asset and writes down remarks in the company's mobile app.
2. **Trigger:** The app uploads the photos to S3 and triggers the enterprise backend system.
3. **API Call:** backend client calls the AI microservice endpoint `POST /api/v1/audit/run`. It passes:
   - The `asset_id` and `asset_spec` (name, model, etc.)
   - The S3 paths to the uploaded photos (`s3_image_keys`)
   - The auditor's written notes (`auditor_remarks`)

---

## Step 3: The Multi-Agent LangGraph Pipeline

Once the `/audit/run` endpoint is hit, the AI kicks off a LangGraph State Machine. This is not a single prompt, but rather a team of 5 specialized AI "agents" working sequentially. The system streams its progress back to backend client using NDJSON, so the auditor sees live updates (e.g., "Agent 1 analyzing documents... Agent 2 analyzing images...").

### 1. Document Agent
- **Goal:** Find the specific rules that apply to this exact asset.
- **Action:** It converts the `asset_spec` and auditor remarks into a query, retrieves a broad dense candidate set from Pinecone, and combines dense similarity with BM25 keyword scores. If enabled, FlashRank performs a final cross-encoder rerank. The selected child matches are supplied with their parent context.

### 2. Image Agent
- **Goal:** Act as the "eyes" of the audit.
- **Action:** It downloads the field photos from S3, encodes them into Base64 formats, and feeds them into a Vision LLM (like GPT-4o or Claude 3.5 Sonnet). It asks the LLM to identify defects, condition severity, and legible text (like serial numbers).
- **Output:** A structured list of findings (e.g., "Finding 1: Severe oxidation on valve casing").

### 3. Rule Agent
- **Goal:** Cross-reference the reality against the rules.
- **Action:** It looks at the text retrieved by the Document Agent, the findings from the Image Agent, and the `auditor_remarks`. It determines if any rules were broken.
- **Output:** A JSON array of violated rules. If a rule says "No rust allowed" and the image agent found rust, this agent flags it.

### 4. Evidence Agent
- **Goal:** Build the legal/compliance paper trail.
- **Action:** It creates an "Evidence Bundle". For every rule triggered by the Rule Agent, the Evidence agent clearly links *why* it was triggered (e.g., "Rule 42 was triggered *because* of photo `photo1.jpg` and the auditor remark 'valve is stuck'").

### 5. Verdict Agent
- **Goal:** Make the final call.
- **Action:** Acting as the Senior Auditor, it reviews the Evidence Bundle and historical past verdicts. It outputs a final structured compliance decision: `COMPLIANT`, `NON_COMPLIANT`, or `NEEDS_REVIEW`. It also generates actionable recommendations (e.g., "Schedule immediate maintenance for valve casing").

---

## Step 4: Auditor Chat (The Q&A RAG System)

After the audit, or during an inspection, the auditor might have questions (e.g., "What is the maximum torque for this bolt?").

1. **API Call:** The auditor asks a question via the `POST /api/v1/chat/query` endpoint.
2. **Tier 1 (Document Retrieval):** The AI embeds the question, runs dense/BM25 hybrid candidate scoring, and optionally reranks the results. If the original dense similarity indicates a sufficiently relevant match, it answers using child text plus parent context and cites the PDF page.
3. **Tier 2 (Asset Spec Fallback):** If Pinecone doesn't have the answer, the AI attempts to answer using the asset's basic metadata or previous audit history.
4. **Tier 3 (Web Search):** If the internal data isn't enough, the AI safely searches the public web (using DuckDuckGo or Tavily). It injects the web findings into the prompt but explicitly warns the auditor: *"According to a web search, the answer is..."*

---

## Step 5: GDPR and Data Erasure

If the company decides to delete an asset from their system, they must comply with data retention and GDPR laws.

1. **API Call:** backend client calls `DELETE /api/v1/admin/assets/{asset_id}`.
2. **Action:** The AI microservice acts autonomously to wipe the asset:
   - It connects to Pinecone and deletes the entire vector namespace for that asset.
   - It connects to S3 and permanently deletes all ingested PDFs and audit photos associated with that asset prefix.
   - It connects to DynamoDB and marks any historical audit logs as `ERASED`.
