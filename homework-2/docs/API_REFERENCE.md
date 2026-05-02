# 🌐 API Reference — Customer Support Ticket System

> Audience: API consumers — frontend developers, third-party integrators, mobile clients.

**Base URL (local):** `http://localhost:8000`
**OpenAPI / Swagger UI:** `http://localhost:8000/docs`
**OpenAPI JSON:** `http://localhost:8000/openapi.json`

**Auth:** none (out of scope for this homework). All endpoints are public.

---

## Endpoint summary

| Method | Endpoint | Purpose | Status codes |
|---|---|---|---|
| `GET` | `/healthz` | Liveness probe | 200 |
| `POST` | `/tickets` | Create ticket (optional `?auto_classify=true`) | 201, 422 |
| `GET` | `/tickets` | List tickets with filters & pagination | 200 |
| `GET` | `/tickets/{ticket_id}` | Get a single ticket by UUID | 200, 404 |
| `PUT` | `/tickets/{ticket_id}` | Partial update | 200, 404, 422 |
| `DELETE` | `/tickets/{ticket_id}` | Delete | 204, 404 |
| `POST` | `/tickets/import` | Bulk import (CSV/JSON/XML) | 200, 400, 413 |
| `POST` | `/tickets/{ticket_id}/auto-classify` | Apply rule-based classifier and persist | 200, 404 |

---

## Data models

### `TicketRead` (response shape)

```json
{
  "id": "5e0c...uuid",
  "customer_id": "cust-1234",
  "customer_email": "alice@example.com",
  "customer_name": "Alice",
  "subject": "Cannot login",
  "description": "I am unable to log in from any browser.",
  "category": "account_access",
  "priority": "urgent",
  "status": "new",
  "created_at": "2026-05-02T11:23:45.123456+00:00",
  "updated_at": "2026-05-02T11:23:45.123456+00:00",
  "resolved_at": null,
  "assigned_to": null,
  "tags": ["billing", "p0"],
  "metadata": {
    "source": "web_form",
    "browser": "Chrome 120",
    "device_type": "desktop"
  },
  "classification_confidence": 0.5
}
```

### Field constraints

| Field | Type | Required | Constraints |
|---|---|---|---|
| `customer_id` | string | yes | 1–255 chars |
| `customer_email` | email | yes | RFC 5322 |
| `customer_name` | string | yes | 1–255 chars |
| `subject` | string | yes | 1–200 chars |
| `description` | string | yes | 10–2000 chars |
| `category` | enum | no (default `other`) | `account_access` \| `technical_issue` \| `billing_question` \| `feature_request` \| `bug_report` \| `other` |
| `priority` | enum | no (default `medium`) | `urgent` \| `high` \| `medium` \| `low` |
| `status` | enum | no (default `new`) | `new` \| `in_progress` \| `waiting_customer` \| `resolved` \| `closed` |
| `assigned_to` | string \| null | no | up to 255 chars |
| `tags` | array of string | no | empty array by default |
| `metadata.source` | enum \| null | no | `web_form` \| `email` \| `api` \| `chat` \| `phone` |
| `metadata.browser` | string \| null | no | free-form |
| `metadata.device_type` | enum \| null | no | `desktop` \| `mobile` \| `tablet` |
| `classification_confidence` | float \| null | system-managed | `[0.0, 1.0]` |

### Error response

```json
{
  "detail": "Ticket not found"
}
```

For Pydantic validation failures (422):

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "customer_email"],
      "msg": "value is not a valid email address: ...",
      "input": "not-an-email"
    }
  ]
}
```

---

## `GET /healthz`

Liveness probe. Always returns `200`.

```bash
curl http://localhost:8000/healthz
# {"status":"ok"}
```

---

## `POST /tickets`

Create a new ticket. Returns the persisted entity (with `id`, `created_at`, defaults applied).

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `auto_classify` | bool | `false` | If `true`, run classifier immediately after insert and persist `category`, `priority`, `classification_confidence`. |

**Request body:** see [Field constraints](#field-constraints). Minimum required fields: `customer_id`, `customer_email`, `customer_name`, `subject`, `description`.

```bash
curl -X POST http://localhost:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust-1",
    "customer_email": "alice@example.com",
    "customer_name": "Alice",
    "subject": "Cannot login",
    "description": "I am unable to log in. Critical, production down."
  }'
```

**With auto-classify:**

```bash
curl -X POST 'http://localhost:8000/tickets?auto_classify=true' \
  -H "Content-Type: application/json" \
  -d '{ ... same body ... }'
```

**Response 201:** full `TicketRead` JSON.
**Response 422:** validation error (e.g. invalid email, description too short).

---

## `GET /tickets`

List tickets, ordered by `created_at` descending. Supports server-side filtering and pagination.

**Query params:**

| Param | Type | Default | Range / values |
|---|---|---|---|
| `category` | enum | (all) | see [enums](#field-constraints) |
| `priority` | enum | (all) | |
| `status` | enum | (all) | |
| `customer_id` | string | (all) | exact match |
| `assigned_to` | string | (all) | exact match |
| `limit` | int | `50` | `[1, 200]` |
| `offset` | int | `0` | `>= 0` |

**Response 200:**

```json
{
  "items": [ /* array of TicketRead */ ],
  "total": 1234,
  "limit": 50,
  "offset": 0
}
```

```bash
# All urgent billing tickets, page 1 (50 per page)
curl 'http://localhost:8000/tickets?category=billing_question&priority=urgent&limit=50&offset=0'

# Open tickets assigned to a specific agent
curl 'http://localhost:8000/tickets?assigned_to=agent-007&status=in_progress'

# Pagination
curl 'http://localhost:8000/tickets?limit=20&offset=40'
```

---

## `GET /tickets/{ticket_id}`

```bash
curl http://localhost:8000/tickets/5e0c1234-1234-4abc-8def-000000000000
```

**Response 200:** `TicketRead` JSON.
**Response 404:** `{"detail": "Ticket not found"}`.

---

## `PUT /tickets/{ticket_id}`

Partial update — every field is optional. Fields not present in the body are preserved as-is.

Special behaviour:
- `metadata: null` → resets stored metadata to `{}`
- `metadata: { ... }` → fully replaces stored metadata
- `tags: null` → resets to `[]`
- `tags: [ ... ]` → fully replaces
- All other fields: standard partial update

```bash
# Assign and progress
curl -X PUT http://localhost:8000/tickets/5e0c.../ \
  -H "Content-Type: application/json" \
  -d '{"assigned_to": "agent-007", "status": "in_progress"}'

# Manual override of auto-classified category/priority
curl -X PUT http://localhost:8000/tickets/5e0c.../ \
  -H "Content-Type: application/json" \
  -d '{"category": "feature_request", "priority": "low"}'

# Resolve
curl -X PUT http://localhost:8000/tickets/5e0c.../ \
  -H "Content-Type: application/json" \
  -d '{"status": "resolved", "resolved_at": "2026-05-02T15:00:00+00:00"}'
```

**Response 200:** `TicketRead` after update.
**Response 404 / 422:** standard error.

---

## `DELETE /tickets/{ticket_id}`

```bash
curl -X DELETE http://localhost:8000/tickets/5e0c.../
```

**Response 204:** empty body.
**Response 404:** ticket missing.

---

## `POST /tickets/import`

Bulk import from a single file. Format detected by extension (`.csv`, `.json`, `.xml`).

**Request:** `multipart/form-data` with field `file`.
**Limits:**
- File size: `MAX_UPLOAD_SIZE_BYTES` env var (default 512 MiB). Exceeding → `413`.
- Unsupported extension → `400`.

**Per-row behaviour:** every record is independently validated by `TicketCreate`. If validation fails, the row is added to `errors[]` (with 1-based row index and reason). If parsing of the **whole file** fails (malformed CSV/JSON/XML), `total = 0`, `failed = 1`, and a single error with `row = 0` is returned.

```bash
# CSV
curl -X POST http://localhost:8000/tickets/import \
  -F "file=@tests/fixtures/sample_tickets.csv"

# JSON
curl -X POST http://localhost:8000/tickets/import \
  -F "file=@tests/fixtures/sample_tickets.json"

# XML
curl -X POST http://localhost:8000/tickets/import \
  -F "file=@tests/fixtures/sample_tickets.xml"
```

**Response 200 (`ImportSummary`):**

```json
{
  "total": 50,
  "successful": 48,
  "failed": 2,
  "errors": [
    {"row": 7, "error": "customer_email: value is not a valid email address: ..."},
    {"row": 22, "error": "description: String should have at least 10 characters"}
  ],
  "created_ids": ["uuid-1", "uuid-2", "..."]
}
```

### Expected file shapes

**CSV** — header row required. Recognized columns:
```
customer_id, customer_email, customer_name, subject, description,
category, priority, status, assigned_to, tags,
source, browser, device_type
```
- `tags` is a comma-separated string (e.g. `"billing,vip"`).
- `source` / `browser` / `device_type` go into the `metadata` object.

**JSON** — either a top-level array of ticket objects, or an object with key `tickets`:
```json
[
  {"customer_id": "c1", "customer_email": "a@b.com", ...},
  ...
]
```
or
```json
{"tickets": [{...}, {...}]}
```

**XML** — root `<tickets>`, child `<ticket>` per record:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<tickets>
  <ticket>
    <customer_id>c1</customer_id>
    <customer_email>alice@example.com</customer_email>
    <customer_name>Alice</customer_name>
    <subject>Cannot login</subject>
    <description>...</description>
    <category>account_access</category>
    <priority>urgent</priority>
    <tags><tag>p0</tag><tag>login</tag></tags>
    <metadata>
      <source>web_form</source>
      <browser>Chrome 120</browser>
      <device_type>desktop</device_type>
    </metadata>
  </ticket>
</tickets>
```

---

## `POST /tickets/{ticket_id}/auto-classify`

Apply the rule-based classifier to an existing ticket and persist the result. The ticket's `category`, `priority`, and `classification_confidence` are updated in-place.

```bash
curl -X POST http://localhost:8000/tickets/5e0c.../auto-classify
```

**Response 200 (`ClassificationResult`):**

```json
{
  "category": "account_access",
  "priority": "urgent",
  "confidence": 0.45,
  "reasoning": "Priority: Matched 1/4 'urgent' keyword(s): production down. Category: Matched 3/16 'account_access' keyword(s): login, password, can't access.",
  "keywords_found": ["production down", "login", "password", "can't access"]
}
```

**Response 404:** ticket missing.

### How the classifier decides

- **Priority** — substring matching against keyword sets, with precedence `urgent > high > low > default(medium)`. Default `medium` returns `confidence = 0.5`.
- **Category** — substring matching across 5 categories; the category with the highest match count wins. If no category matches, returns `other` with `confidence = 0.5`.
- **`confidence`** — average of priority and category confidences, each computed as `matched_keywords / total_keywords_in_winning_set`, clamped `[0.0, 1.0]`.
- **Manual override** — clients may always send `PUT /tickets/{id}` with explicit `category` / `priority` to override the classifier's decision.

### Auto-run on creation

Pass `?auto_classify=true` to `POST /tickets` to trigger classification immediately after insert. The returned ticket reflects the classified `category`, `priority`, `classification_confidence`.

---

## Status codes summary

| Code | Meaning |
|---|---|
| 200 | OK (with body) |
| 201 | Created (POST `/tickets`) |
| 204 | No Content (DELETE) |
| 400 | Bad Request — missing filename, unsupported file extension |
| 404 | Not Found — ticket id does not exist |
| 413 | Payload Too Large — bulk upload exceeded `MAX_UPLOAD_SIZE_BYTES` |
| 422 | Unprocessable Entity — Pydantic validation error |
