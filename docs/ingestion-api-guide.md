# Ingestion API Guide

This guide explains how to interact with the marketing ingestion endpoints that were added to the Social Attribution Tool API. It also outlines the required request payloads, the data flow that happens behind the scenes, and the recommended steps to validate the pipeline end-to-end.

## Overview

The ingestion workflow is exposed through two endpoints under `/api/v1/files`:

1. `POST /api/v1/files/upload` — Accepts a CSV/TSV export, stores it on disk, and returns the absolute path of the saved file.
2. `POST /api/v1/files/ingest/path` — Takes the path of an uploaded file, normalizes it, validates required columns, and ingests the data into staging/fact tables while logging the run in `event_ingestion_log`.

Both endpoints are grouped under the **files** tag in the OpenAPI (Swagger) documentation to make them easy to find.

## Request and Response Examples

### 1. Upload a file

```bash
curl -X POST "http://localhost:8000/api/v1/files/upload" \
     -F "file=@/absolute/path/to/DMA_Performance_Meta.csv"
```

**Successful response**
```json
{
  "saved_path": "/app/data/uploads/DMA_Performance_Meta.csv",
  "size_bytes": 12038
}
```

### 2. Trigger ingestion

```bash
curl -X POST "http://localhost:8000/api/v1/files/ingest/path" \
     -H "Content-Type: application/json" \
     -d '{
           "file_path": "/app/data/uploads/DMA_Performance_Meta.csv",
           "column_map": {"platform_id": 1, "account_id": 42},
           "currency_code": "AUD",
           "attribution": "Incremental",
           "dry_run": false,
           "fail_fast": false,
           "batch_size": 500
         }'
```

**Successful response**
```json
{
  "inserted": 250,
  "updated": 12,
  "skipped": 3,
  "warnings": [
    "Row 4: unknown DMA 'Reels & Feeds | US Only' — add a column_map.dma_map entry"
  ],
  "status": "ingested",
  "summary": "Inserted records into the warehouse. Inserted=250, Updated=12, Skipped=3.",
  "duration_sec": 4.21,
  "normalized_path": "/app/data/uploads/DMA_Performance_Meta__normalized.csv"
}
```

## End-to-End Testing Checklist

1. **Start the API server**
   ```bash
   uvicorn app.main:app --reload
   ```

2. **Open Swagger UI** at [http://localhost:8000/docs](http://localhost:8000/docs). Look for the **files** tag, which contains the upload and ingest operations. Use the built-in forms to execute the requests directly from the browser if preferred.

3. **Upload a sample file** using the Swagger UI or the cURL command shown earlier. Confirm that the response includes an absolute path under the server's `data/uploads/` directory.

4. **Kick off ingestion** by calling the ingest endpoint with the `file_path` returned in step 3. Provide any overrides (currency code, attribution, dimension IDs) required for your dataset.

5. **Review the response** to confirm the counts and warnings look correct. The `status` field explains whether rows were ingested, skipped (no data), or if you ran a dry run, while `summary` reiterates the inserted/updated/skipped totals. A `normalized_path` ending with `__normalized.csv` should be returned, indicating the normalization step succeeded.

6. **Verify the event log** by querying the `event_ingestion_log` table. The API writes a record for every ingestion run, including failures, so you can audit the outcomes.

Following this sequence ensures the full upload → normalize → ingest → log pipeline works as expected.

## Additional Notes

- The ingestion service automatically detects delimiter and encoding, drops empty rows, and preserves all columns during normalization.
- Campaign/ad set/ad identifiers are resolved automatically using the names and IDs present in each row. Missing dimensions are created on the fly and reused for subsequent records, but you can override the behaviour with `column_map` keys such as `campaign_id`, `campaign_map`, `adset_map`, or `ad_map`.
- Accounts are seeded automatically when the supplied `column_map.account_id` does not yet exist. Provide optional hints like `account_external_id` or `account_name` (or `account_label`) in the column map to control the values written to `dim_account`.
- To run a dry validation without writing to the database, set `"dry_run": true` in the ingestion request.
- Use `"fail_fast": true` to stop processing on the first validation error; otherwise, warnings are collected and returned in the response.
- Every upload and ingestion call writes structured entries to `data/logs/ingestion.log`. Each line begins with an event label (for example, `UPLOAD_START`, `STAGE_START`, `HEADER_NORMALIZED`, `ROW_READY`, `DATABASE_WRITE_COMPLETE`) followed by key/value details so you can trace the exact step, inputs, and outcomes for the run.

## Log Event Reference

The ingestion log provides a chronological narrative across the major stages:

| Event | Description |
|-------|-------------|
| `UPLOAD_START` / `UPLOAD_STREAM_COMPLETE` / `UPLOAD_COMPLETE` | Captures incoming files, chunk counts, and their saved path on disk. |
| `RESOLVE_PATH_SUCCESS` | Shows how the ingest endpoint resolved the provided `file_path` argument. |
| `STAGE_START` / `STAGE_COMPLETE` | Wraps each major phase (normalization, validation, database write, ingestion pipeline) with human-readable descriptions and outcomes. |
| `INGEST_START` | Lists the normalized options (column map, currency, attribution, dry run flags) supplied for the run. |
| `NORMALIZE_FILE` → `HEADER_NORMALIZED` → `BLANK_ROWS_REMOVED` → `ROW_ALIGNMENT_COMPLETE` → `NORMALIZED_FILE_WRITTEN` → `NORMALIZE_FILE_COMPLETE` | Documents encoding/delimiter detection, header cleanup, row trimming, and creation of the normalized artifact. |
| `VALIDATION_BEGIN` / `VALIDATION_COMPLETE` | Signals when handler-specific validation starts and ends. |
| `ROW_*` events | Provide per-row insight such as missing dates or dimension lookups (`ROW_SKIPPED_*`, `ROW_READY`). |
| `ROW_CAMPAIGN_RESOLVED*`, `ROW_ADSET_RESOLVED*`, `ROW_AD_RESOLVED*` | Show how campaign, ad set, and ad identifiers were sourced (column map override, mapping, or freshly created dimension rows). |
| `PAYLOAD_PREPARED` | Summarizes how many rows are ready after preprocessing, including warnings and a sample payload. |
| `DATABASE_DELETE_SCOPE` / `UPSERT_DETAILS` / `DATABASE_WRITE_BEGIN` / `DATABASE_WRITE_COMPLETE` | Indicates when rows were deleted or upserted, along with conflict keys, inserted counts, and warnings. |
| `EVENT_LOG_WRITE` / `EVENT_LOG_DB_WRITE_BEGIN` / `EVENT_LOG_DB_WRITE_COMPLETE` | Confirms the API recorded the summary row in `event_ingestion_log`. |
| `INGESTION_ERROR` | Emitted when a handler raises an exception; includes the error message and stage context. |

Reviewing the log after an ingestion call will therefore answer whether normalization succeeded, which rows were skipped (and why), and whether database commits actually occurred.

## What happens after normalization?

1. **Handler selection** – Once the normalized copy is produced, the ingestion service finds the first registered handler whose filename pattern matches the request (for example, Meta DMA, Shopify sales, or TikTok region files).
2. **Validation & mapping** – That handler validates the required columns for its dataset, resolves any dimension IDs (DMA, region, campaign, etc.), and prepares the rows for persistence.
3. **Database writes** – Unless `dry_run` is enabled, the handler executes the upsert logic that writes the cleaned data into the appropriate staging or fact tables defined in the warehouse schema.
4. **Event logging** – The service records the outcome in `event_ingestion_log`, capturing counts, status, and runtime so you can audit the ingestion.

No separate API call is required after normalization—the same `/api/v1/files/ingest/path` request performs normalization, validation, database storage, and logging as a single transaction-oriented workflow.

Refer back to this document whenever you need a refresher on the available endpoints or the recommended testing procedure.
