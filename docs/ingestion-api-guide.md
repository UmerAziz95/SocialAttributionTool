# Ingestion API Guide

This guide explains how to interact with the marketing ingestion endpoints that were added to the Social Attribution Tool API. It also outlines the required request payloads, the data flow that happens behind the scenes, and the recommended steps to validate the pipeline end-to-end.

## Overview

The ingestion workflow is exposed through three endpoints under `/api/v1/files`:

1. `POST /api/v1/files/upload` — Accepts one or more CSV/TSV exports plus a required `platform` value (TikTok, Shopify, Meta, Pinterest, or Google). Each file is stored inside `data/uploads/<platform>/`, and the response returns metadata for every saved file.
2. `POST /api/v1/files/normalize` — Walks every platform upload folder (or a requested subset) and normalizes each source file in place. The normalized copy is written beside the original using the `__normalized.csv` suffix, and the response lists the detected encoding, delimiter, header count, and row count per file.
3. `POST /api/v1/files/ingest/platform` — Takes the platform name (and an optional subset of filenames) and automatically normalizes, validates, and ingests **every** file sitting inside that platform's upload folder. Normalized copies are written back next to each original using the `__normalized.csv` suffix, and every handler run is logged to `event_ingestion_log`.

Both endpoints are grouped under the **files** tag in the OpenAPI (Swagger) documentation to make them easy to find.

## Request and Response Examples

### 1. Upload a file

```bash
curl -X POST "http://localhost:8000/api/v1/files/upload" \
     -F "platform=tiktok" \
     -F "files=@/abs/path/to/tiktok_by_dma.csv" \
     -F "files=@/abs/path/to/tiktok_by_region.csv"
```

**Successful response**
```json
{
  "platform": "tiktok",
  "files": [
    {
      "filename": "tiktok_by_dma.csv",
      "saved_path": "/app/data/uploads/tiktok/tiktok_by_dma.csv",
      "size_bytes": 2314
    },
    {
      "filename": "tiktok_by_region.csv",
      "saved_path": "/app/data/uploads/tiktok/tiktok_by_region.csv",
      "size_bytes": 5428
    }
  ]
}
```

### 2. Trigger ingestion

```bash
curl -X POST "http://localhost:8000/api/v1/files/ingest/platform" \
     -H "Content-Type: application/json" \
     -d '{
           "platform": "tiktok",
           "filenames": ["tiktok_by_dma.csv", "tiktok_by_region.csv"],
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
  "platform": "tiktok",
  "results": [
    {
      "filename": "tiktok_by_dma.csv",
      "file_path": "/app/data/uploads/tiktok/tiktok_by_dma.csv",
      "inserted": 250,
      "updated": 12,
      "skipped": 3,
      "warnings": [],
      "status": "ingested",
      "summary": "Inserted records into the warehouse. Inserted=250, Updated=12, Skipped=3.",
      "duration_sec": 4.21,
      "normalized_path": "/app/data/uploads/tiktok/tiktok_by_dma__normalized.csv"
    },
    {
      "filename": "tiktok_by_region.csv",
      "file_path": "/app/data/uploads/tiktok/tiktok_by_region.csv",
      "inserted": 75,
      "updated": 0,
      "skipped": 2,
      "warnings": ["Row 4: missing subregion"],
      "status": "ingested",
      "summary": "Inserted records into the warehouse. Inserted=75, Updated=0, Skipped=2.",
      "duration_sec": 2.10,
      "normalized_path": "/app/data/uploads/tiktok/tiktok_by_region__normalized.csv"
    }
  ]
}
```

### 3. Normalize uploaded files (optional pre-check)

```bash
curl -X POST "http://localhost:8000/api/v1/files/normalize" \\
     -H "Content-Type: application/json" \\
     -d '{
           "platforms": ["tiktok", "meta"]
         }'
```

**Successful response**
```json
{
  "results": [
    {
      "platform": "tiktok",
      "filename": "tiktok_by_dma.csv",
      "source_path": "/app/data/uploads/tiktok/tiktok_by_dma.csv",
      "normalized_path": "/app/data/uploads/tiktok/tiktok_by_dma__normalized.csv",
      "row_count": 42867,
      "header_count": 21,
      "encoding": "latin-1",
      "delimiter": "\t",
      "status": "normalized",
      "detail": "Normalized successfully"
    }
  ]
}
```

## End-to-End Testing Checklist

1. **Start the API server**
   ```bash
   uvicorn app.main:app --reload
   ```

2. **Open Swagger UI** at [http://localhost:8000/docs](http://localhost:8000/docs). Look for the **files** tag, which contains the upload and ingest operations. Use the built-in forms to execute the requests directly from the browser if preferred.

3. **Upload the files for a platform** using the Swagger UI or the cURL command shown earlier. Confirm that each response entry includes an absolute path under the server's `data/uploads/<platform>/` directory.

4. **(Optional) Run the normalization sweep** via `POST /api/v1/files/normalize` to confirm every upload can be standardized successfully. Specify a subset of platforms if you only need to refresh a portion of the dataset; otherwise, omit the payload to scan all folders.

5. **Kick off ingestion** by calling the platform ingest endpoint with the `platform` you uploaded under. Optionally include a `filenames` array to limit the run to specific files; if omitted, the API iterates over every non-normalized file in that platform folder. Provide any overrides (currency code, attribution, dimension IDs) required for your dataset.

6. **Review the response** to confirm the per-file counts and warnings look correct. Each entry explains whether rows were ingested, skipped (no data), or part of a dry run, while `summary` reiterates the inserted/updated/skipped totals. Every entry also reports the `normalized_path` ending with `__normalized.csv`, indicating the normalization step succeeded.

7. **Verify the event log** by querying the `event_ingestion_log` table. The API writes a record for every ingestion run, including failures, so you can audit the outcomes.

Following this sequence ensures the full upload → normalize → ingest → log pipeline works as expected.

## Additional Notes

- The ingestion service automatically detects delimiter and encoding, drops empty rows, and preserves all columns during normalization. The normalized copy is written back to the same platform directory as the original file using the `__normalized.csv` suffix so you always have a side-by-side artifact (and now each platform folder contains both the uploads and their normalized counterparts).
- Campaign/ad set/ad identifiers are resolved automatically using the names and IDs present in each row. Missing dimensions are created on the fly and reused for subsequent records, but you can override the behaviour with `column_map` keys such as `campaign_id`, `campaign_map`, `adset_map`, or `ad_map`.
- DMA labels are resolved automatically. The service first looks for an explicit `column_map.dma_map` override, then for an existing `map_platform_dma` row, and finally creates the `dim_dma` + `map_platform_dma` records when a new label is encountered. Vendor suffixes such as `,DMA®`, `DMA`, or `DMA Region` are stripped automatically before the lookup so that `Syracuse,DMA®` and `Syracuse DMA` collapse onto the same dimension key. Common placeholder values such as `Unknown`, `Not Reported`, or `N/A` are treated as unspecified and logged via `ROW_DMA_TREATED_AS_NULL` so the fact row is written with a `NULL` `dma_id`. If a non-placeholder label still cannot be mapped after those checks, the row is ingested with a warning (`ROW_DMA_UNRESOLVED`) so you can backfill a mapping later without losing the metric values.
- Region columns behave similarly: unresolved entries generate a `ROW_REGION_UNRESOLVED` event, keep the row in the payload with a `NULL` `region_id`, and emit a warning so you can add `column_map.region_map` hints without re-running normalization.
- Accounts are seeded automatically when the supplied `column_map.account_id` does not yet exist. Provide optional hints like `account_external_id` or `account_name` (or `account_label`) in the column map to control the values written to `dim_account`.
- Platforms are also created on demand when the specified `column_map.platform_id` is missing; include `platform_name` or `platform_label` in the column map to set the `dim_platform.name` value.
- To run a dry validation without writing to the database, set `"dry_run": true` in the ingestion request.
- Use `"fail_fast": true` to stop processing on the first validation error; otherwise, warnings are collected and returned in the response.
- Every upload and ingestion call writes structured entries to `data/logs/ingestion.log`. Each line begins with an event label (for example, `UPLOAD_START`, `STAGE_START`, `HEADER_NORMALIZED`, `ROW_READY`, `DATABASE_WRITE_COMPLETE`) followed by key/value details so you can trace the exact step, inputs, and outcomes for the run. When uploading multiple files, the log will include individual `UPLOAD_*` events for each filename together with the `platform` that owns the directory.

## Log Event Reference

The ingestion log provides a chronological narrative across the major stages:

| Event | Description |
|-------|-------------|
| `UPLOAD_START` / `UPLOAD_STREAM_COMPLETE` / `UPLOAD_COMPLETE` | Captures incoming files, chunk counts, and their saved path on disk. |
| `RESOLVE_PATH_SUCCESS` | Shows how the ingest endpoint resolved a requested filename inside the platform directory. |
| `STAGE_START` / `STAGE_COMPLETE` | Wraps each major phase (normalization, validation, database write, ingestion pipeline) with human-readable descriptions and outcomes. |
| `INGEST_START` | Lists the normalized options (column map, currency, attribution, dry run flags) supplied for the run. |
| `NORMALIZE_FILE` → `HEADER_NORMALIZED` → `BLANK_ROWS_REMOVED` → `ROW_ALIGNMENT_COMPLETE` → `NORMALIZED_FILE_WRITTEN` → `NORMALIZE_FILE_COMPLETE` | Documents encoding/delimiter detection, header cleanup, row trimming, and creation of the normalized artifact. |
| `VALIDATION_BEGIN` / `VALIDATION_COMPLETE` | Signals when handler-specific validation starts and ends. |
| `ROW_*` events | Provide per-row insight such as missing dates or dimension lookups (`ROW_DMA_AUTO_MAPPED`, `ROW_DMA_RESOLVED_MAPPING`, `ROW_DMA_TREATED_AS_NULL`, `ROW_DMA_UNRESOLVED`, `ROW_REGION_UNRESOLVED`, `ROW_SKIPPED_*`, `ROW_READY`). |
| `PLATFORM_DIMENSION_ENSURED` / `ACCOUNT_DIMENSION_ENSURED` | Confirm that prerequisite platform/account records existed or were auto-created before campaign resolution. |
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

No separate API call is required after normalization—the same `/api/v1/files/ingest/platform` request performs normalization, validation, database storage, and logging for every matching file as a single transaction-oriented workflow.

Refer back to this document whenever you need a refresher on the available endpoints or the recommended testing procedure.
