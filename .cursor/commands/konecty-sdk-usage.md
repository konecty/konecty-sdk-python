# Konecty SDK Python — Complete usage guide

**Command instruction:** When the user asks about or uses the Konecty SDK Python in this project, follow the documentation below as the only reference. Do not reference other files or external docs; everything needed is in this document.

---

Use this as the single source of truth when writing or reviewing code that uses the **Konecty SDK Python** (package `KonectySdkPython` or `konecty-sdk-python`). Assume the project has the SDK installed (e.g. `pip install konecty-sdk-python`). All information needed is below.

---

## 1. What the SDK is

The Konecty SDK Python is a client library for the [Konecty](https://github.com/konecty/Konecty) CRM REST API. It provides:

- **KonectyClient** — Async REST client: CRUD, find, find stream, count, file upload/download, export, KPI/graph/pivot, comments, subscriptions, notifications, change user, custom query (JSON/SQL), saved queries.
- **Types and filters** — Pydantic models for Konecty data and filter/sort builders for queries.
- **Feature types** — KpiConfig, CrossModuleQuery/CrossModuleRelation for aggregations and custom queries.
- **FileManager** — Used internally for uploads; upload is exposed via `client.upload_file`.
- **Settings** — `fill_settings` / `fill_settings_sync` to populate a config class from env + Konecty Setting module.
- **CLI** — `konecty-cli` (apply, backup, pull) for metadata operations; not for business data CRUD.

---

## 2. Environment and setup

- **KONECTY_URL** — Base URL of the Konecty API (e.g. `https://your-instance.konecty.com`). Default if unset: `http://localhost:3000`.
- **KONECTY_TOKEN** — Token sent in the `Authorization` header. The SDK does **not** add a "Bearer" prefix; use the exact token Konecty expects (e.g. from login or API key).

Example:

```python
import os
from KonectySdkPython import KonectyClient

client = KonectyClient(
    base_url=os.environ.get("KONECTY_URL", "http://localhost:3000"),
    token=os.environ["KONECTY_TOKEN"],
)
```

All data methods on the client are **async** except where noted (e.g. `find_sync`, `get_setting_sync`). Use `await client.find(...)` in async code or run the client in an async context.

---

## 3. Imports (public API)

From the package root (`KonectySdkPython`):

- **Client and filters:** `KonectyClient`, `KonectyDict`, `KonectyFilter`, `KonectyFindParams`
- **File:** `FileManager`
- **Model generation:** `KonectyModelGenerator`
- **Settings:** `fill_settings`, `fill_settings_sync`
- **Types:** `KonectyAddress`, `KonectyBaseModel`, `KonectyDateTime`, `KonectyEmail`, `KonectyLabel`, `KonectyLookup`, `KonectyPersonName`, `KonectyPhone`, `KonectyUser`, `KonectyUpdateId`
- **Exceptions:** `KonectyError`, `KonectyAPIError`, `KonectyValidationError` (from client)

From `KonectySdkPython.lib.filters`: `FilterOperator`, `FilterMatch`, `SortOrder`, `SortDirection`, `FilterCondition` (for building filters by hand).

From `KonectySdkPython.lib.client`: `FindStreamResult` (result of `find_stream`).

From `KonectySdkPython.lib.feature_types`: `KpiConfig`, `KpiOperation`, `CrossModuleQuery`, `CrossModuleRelation`, `Aggregator`, and constants `MAX_RELATIONS`, `MAX_RELATION_LIMIT`, `DEFAULT_PRIMARY_LIMIT`.

Query result type: `QueryResult` from `KonectySdkPython.lib` (or the query service module) for `execute_query_json` / `execute_query_sql`.

---

## 4. Module (document) names

The `module` parameter is the **Konecty document type name** (e.g. `Contact`, `User`, `Setting`), not a URL path. Get document names from the Konecty app or from `client.get_document(document_id)` / `client.get_schema(document_id)`.

---

## 5. CRUD and find

- **Find:** `await client.find(module, options)` — `options` is `KonectyFindParams(filter=..., start=..., limit=..., sort=..., fields=...)`. Returns `List[KonectyDict]`.
- **Find sync:** `client.find_sync(module, options)` — same contract, blocking.
- **Find one:** `await client.find_one(module, filter_params)` or `client.find_one_sync(module, filter_params)` — returns one record or `None`.
- **By ID:** `await client.find_by_id(module, id)` — returns one record or `None`.
- **Create:** `await client.create(module, data)` — `data` is a dict; do not send `_createdAt`, `_updatedAt`, `_createdBy`, `_updatedBy` (SDK strips them). Returns created record or `None`.
- **Update one:** `await client.update_one(module, id, updatedAt, data)` — requires current `_updatedAt` for optimistic concurrency.
- **Update many:** `await client.update(module, ids, data)` — `ids` is a list of `KonectyUpdateId` (each has `_id` and `_updatedAt`). Use `KonectyUpdateId.from_dict(record)` from a fetched record.
- **Delete one:** `await client.delete_one(module, id, updatedAt)` — requires current `_updatedAt`.

On API failure (e.g. validation, permission), the client raises **KonectyAPIError** with the errors list from the response.

---

## 6. Building filters and find options

- **Filter:** `KonectyFilter.create(match="and")` or `match="or"`, then `.add_condition(term, operator, value)`. Operators: `equals`, `not_equals`, `in`, `not_in`, `less_than`, `greater_than`, `less_or_equals`, `greater_or_equals`, `between`, `exists`, `contains`, `starts_with`, `end_with`, `not_contains` (use `FilterOperator` enum or lowercase strings). Nested filters: `.add_filter(match)` returns a child filter to which you add conditions.
- **Sort:** `KonectyFindParams(..., sort=[SortOrder(property="fieldName", direction=SortDirection.DESC)], ...)`.
- **Pagination:** `start` and `limit` on `KonectyFindParams`.
- **Fields:** `fields` as list of field names, e.g. `["_id", "name"]`.

Example:

```python
from KonectySdkPython import KonectyClient, KonectyFilter, KonectyFindParams
from KonectySdkPython.lib.filters import SortOrder, SortDirection

filter_params = KonectyFilter.create().add_condition("status", "equals", "Open")
options = KonectyFindParams(filter=filter_params, limit=10, sort=[SortOrder(property="name", direction=SortDirection.ASC)])
records = await client.find("Contact", options)
```

---

## 7. Stream and count

- **Find stream:** `await client.find_stream(module, options, include_total=False)` — returns **FindStreamResult** with `.stream` (async generator of dicts) and `.total` (int or None). Consume with `async for record in result.stream:`; use `result.total` after or during iteration when `include_total=True`.
- **Count stream:** `await client.count_stream(module, filter_params=None, **kwargs)` — returns total count (int). Dedicated endpoint for count; alternative to `count_documents` with find.

---

## 8. Files: upload and download

- **Upload:** `await client.upload_file(module, record_code, field_name, file, file_name=None, file_type=None)` — `file` can be bytes, path (str), or `AsyncGenerator[bytes, None]`. Returns file key (str). Do not send Bearer in token; SDK sends token as-is.
- **Download file:** `await client.download_file(module, record_code, field_name, file_name)` — returns **bytes**.
- **Download image:** `await client.download_image(module, record_id, field_name, file_name, style=None)` — returns **bytes**. `style` can be `"full"`, `"thumb"`, or `"wm"` (watermark); `None` means full.

---

## 9. Export

- **Export list:** `await client.export_list(module, list_name, format, filter_params=None, **kwargs)` — `format` is `"csv"`, `"xlsx"`, `"json"`, or `"xls"` (normalized to xlsx). Returns **bytes** (file content). Optional kwargs: sort, fields, start, limit, display_name, display_type.

---

## 10. Aggregations: KPI, Graph, Pivot

- **KPI:** `await client.get_kpi(module, kpi_config, filter_params=None, **kwargs)` — `kpi_config` is **KpiConfig** from `KonectySdkPython.lib.feature_types`: `KpiConfig(operation="count")` or `operation` in `count`, `sum`, `avg`, `min`, `max`, `countDistinct`; for `countDistinct`, `field` is required. Returns dict with `value` and `count`.
- **Graph:** `await client.get_graph(module, graph_config, filter_params=None, **kwargs)` — `graph_config` is a dict (or Pydantic model) with `type` (e.g. bar, line, pie, scatter, histogram, timeSeries), `xAxis`, `yAxis`, `series`, etc. Returns **str** (SVG).
- **Pivot:** `await client.get_pivot(module, pivot_config, filter_params=None, **kwargs)` — `pivot_config` has `rows`, `columns`, `values`. Returns **dict** (API result).

---

## 11. Comments

- **List:** `await client.get_comments(module, data_id)` — returns API result (success, data).
- **Create:** `await client.create_comment(module, data_id, text, parent_id=None)` — `parent_id` for replies.
- **Update:** `await client.update_comment(module, data_id, comment_id, text)`.
- **Delete:** `await client.delete_comment(module, data_id, comment_id)`.
- **Search users (mention):** `await client.search_comment_users(module, data_id, query="")`.
- **Search comments:** `await client.search_comments(module, data_id, query=None, author_id=None, start_date=None, end_date=None, page=None, limit=None)`.

---

## 12. Subscriptions and notifications

- **Subscription status:** `await client.get_subscription_status(module, data_id)`.
- **Subscribe / Unsubscribe:** `await client.subscribe(module, data_id)`, `await client.unsubscribe(module, data_id)`.
- **Notifications:** `await client.list_notifications(read=None, page=None, limit=None)`, `await client.get_unread_notifications_count()`, `await client.mark_notification_read(notification_id)`, `await client.mark_all_notifications_read()`.

---

## 13. Change user (assignments, queue)

All take `module` and `ids` (list of record ids). Where users or queue are needed, pass as next args.

- **Add users:** `await client.change_user_add(module, ids, users)`.
- **Remove users:** `await client.change_user_remove(module, ids, users)`.
- **Define users:** `await client.change_user_define(module, ids, users)`.
- **Replace user:** `await client.change_user_replace(module, ids, from_user=..., to_user=...)`.
- **Count inactive:** `await client.change_user_count_inactive(module, ids)`.
- **Remove inactive:** `await client.change_user_remove_inactive(module, ids)`.
- **Set queue:** `await client.change_user_set_queue(module, ids, queue)`.

---

## 14. Custom query (query/json and query/sql)

Execute cross-module queries without saving them.

- **Execute JSON:** `await client.execute_query_json(body, include_total=True, include_meta=False)` — `body` is a **CrossModuleQuery** (dict or model from `KonectySdkPython.lib.feature_types`). Structure: `document` (required), `filter`, `fields`, `sort`, `limit` (default 1000), `start` (default 0), `relations` (array, max 10), `groupBy`, `aggregators`, `includeTotal`, `includeMeta`. Each relation: `document`, `lookup`, `on` (optional left/right), `filter`, `fields`, `sort`, `limit`, `start`, `aggregators` (required, at least one), `relations` (nested, max 10). Returns **QueryResult** with `.stream` (async generator of record dicts), `.total` (int or None), `.meta` (dict or None). Server response is NDJSON; first line may be `_meta` (when includeMeta); then one JSON object per record. Header `X-Total-Count` when includeTotal.
- **Execute SQL:** `await client.execute_query_sql(sql, include_total=True, include_meta=False)` — server converts SQL to CrossModuleQuery (MySQL-like, **SELECT only**, max length 10_000 characters). Same **QueryResult**. On SQL parse error the server returns 400 with errors in `_meta`; SDK raises **KonectyAPIError**.

Example (JSON):

```python
from KonectySdkPython.lib.feature_types import CrossModuleQuery

body = {"document": "Contact", "limit": 100, "includeTotal": True}
result = await client.execute_query_json(body, include_total=True)
async for record in result.stream:
    print(record)
total = result.total
```

Example (SQL):

```python
result = await client.execute_query_sql("SELECT _id, name FROM Contact LIMIT 50")
async for record in result.stream:
    print(record)
```

Caveats: stream is single-use (do not iterate twice); for large result sets consider timeout and memory; SQL has server-side limits (SELECT only, 10k chars); permissions apply per document.

---

## 15. Saved queries (CRUD and share)

- **List:** `await client.list_saved_queries()`.
- **Get:** `await client.get_saved_query(query_id)`.
- **Create:** `await client.create_saved_query(name, query, description=None)` — `query` is a CrossModuleQuery dict (or model).
- **Update:** `await client.update_saved_query(query_id, name=None, description=None, query=None)`.
- **Delete:** `await client.delete_saved_query(query_id)`.
- **Share:** `await client.share_saved_query(query_id, shared_with, is_public=None)` — `shared_with` is list of dicts (e.g. `{ "type": "user", "_id": "...", "name": "..." }`).

---

## 16. Document, schema, settings

- **Document metadata:** `await client.get_document(document_id)`, `await client.get_schema(document_id)` — return metadata for the document type.
- **Settings:** `await client.get_setting(key)`, `await client.get_settings(keys)` (async); `client.get_setting_sync(key)`, `client.get_settings_sync(keys)` (sync). They query the **Setting** module. Use **fill_settings(YourSettingsClass)** (async) or **fill_settings_sync(YourSettingsClass)** to fill a Pydantic settings class from env first, then Konecty Setting keys.

---

## 17. Types for updates and payloads

- **KonectyDateTime:** Konecty format `{"$date": "ISO8601"}`. Use `KonectyDateTime.from_datetime(dt)` and `.to_json()` for update/delete payloads.
- **KonectyUpdateId:** For update/delete bodies, use `KonectyUpdateId.from_dict({"_id": id, "_updatedAt": ...})` from a fetched record; `.to_dict()` for the request. Always use the **current** `_updatedAt` of the record; Konecty uses it for optimistic concurrency.
- **KonectyBaseModel:** Base for document models; `to_dict()`, `to_update_dict()`, `from_dict()`, `from_json()`.
- **KonectyPhone**, **KonectyEmail**, **KonectyPersonName**, **KonectyLookup**, **KonectyAddress:** Use for type-safe field values when building or parsing records.

---

## 18. CLI (konecty-cli)

The CLI is for **metadata** (MongoDB), not for business data CRUD. Commands: **apply** (apply metadata to MongoDB), **backup** (backup metadata), **pull** (pull metadata from API or MongoDB). Require `--mongo-url`, `--database`; for API, Konecty URL and token must be configured. For CRUD on business data, use **KonectyClient** only.

---

## 19. Common pitfalls

- **Authorization:** The SDK sends the token as-is in the `Authorization` header (no "Bearer" prefix). Use the same token format Konecty expects.
- **Update/delete:** Always pass the current `_updatedAt` of the record. After a find, use that record’s `_updatedAt` for `update_one` or `delete_one`; otherwise Konecty may reject for concurrency.
- **Module name:** Always use the Konecty document name (e.g. `Contact`, `User`, `Setting`), not a URL or internal id.
- **Filter serialization:** Use `KonectyFilter` and `KonectyFindParams` so the SDK serializes filters correctly (e.g. datetimes as `$date`). Do not build raw JSON by hand unless you match Konecty’s format.
- **Stream consumption:** `FindStreamResult.stream` and `QueryResult.stream` are async generators; consume once. Access `.total` and `.meta` after or during iteration as documented.
- **Errors:** On API errors the client raises **KonectyAPIError**; catch it and use the attached errors list for user feedback or logging.

---

## 20. Examples (from Konecty tests and integrations)

The following examples are adapted from Konecty’s test suites (e.g. graphStream.test.ts, pivotStream.test.ts, queryApi.test.ts, crossModuleQuery.integration.test.ts, runGraphIntegrationTest.ts). Use them as reference for payload shape and SDK usage.

### Find with filter and pagination

```python
from KonectySdkPython import KonectyClient, KonectyFilter, KonectyFindParams

client = KonectyClient(base_url="https://your.konecty.com", token="your-token")
filter_params = KonectyFilter.create().add_condition("status", "equals", "Open")
options = KonectyFindParams(filter=filter_params, limit=10, start=0)
records = await client.find("Contact", options)
```

### Find stream with total

```python
options = KonectyFindParams(filter=KonectyFilter.create().add_condition("status", "in", ["Nova", "Em Visitação"]), limit=100)
result = await client.find_stream("Opportunity", options, include_total=True)
async for record in result.stream:
    process(record)
total = result.total  # total count when include_total=True
```

### Graph — bar chart (count by category)

Same structure as in Konecty’s graphStream.test and runGraphIntegrationTest: type bar, categoryField, aggregation count, xAxis/yAxis.

```python
graph_config = {
    "type": "bar",
    "categoryField": "status",
    "aggregation": "count",
    "xAxis": {"field": "status", "label": "Status"},
    "yAxis": {"field": "code", "label": "Quantidade"},
    "title": "Oportunidades por Status",
}
filter_params = KonectyFilter.create().add_condition("status", "in", ["Nova", "Em Visitação", "Contrato"])
svg = await client.get_graph("Opportunity", graph_config, filter_params=filter_params, limit=1000)
# svg is full SVG string; save to file or embed in HTML
```

### Graph — bar chart (sum aggregation)

```python
graph_config = {
    "type": "bar",
    "categoryField": "status",
    "aggregation": "sum",
    "xAxis": {"field": "status", "label": "Status"},
    "yAxis": {"field": "amount.value", "label": "Valor Total"},
    "title": "Valor Total por Status",
}
svg = await client.get_graph("Opportunity", graph_config, filter_params=filter_params, limit=1000)
```

### Graph — pie chart

```python
graph_config = {
    "type": "pie",
    "categoryField": "status",
    "aggregation": "count",
    "yAxis": {"field": "code"},
    "title": "Distribuição por Status",
}
svg = await client.get_graph("Opportunity", graph_config, filter_params=filter_params, limit=1000)
```

### Pivot — rows, columns, values

Same structure as in pivotStream.test: rows/columns/values with aggregator.

```python
pivot_config = {
    "rows": [{"field": "status"}],
    "columns": [{"field": "type"}],
    "values": [{"field": "value", "aggregator": "sum"}],
}
result = await client.get_pivot("Opportunity", pivot_config, filter_params=filter_params)
# result contains data, grandTotals (cells, totals), etc.
```

### Custom query (JSON) — Contact + Opportunity with count

From queryApi.test and crossModuleQuery.integration.test: document Contact, relation Opportunity via lookup contact, aggregator count.

```python
body = {
    "document": "Contact",
    "limit": 1000,
    "includeTotal": True,
    "includeMeta": False,
    "relations": [
        {
            "document": "Opportunity",
            "lookup": "contact",
            "aggregators": {"activeOpportunities": {"aggregator": "count"}},
        },
    ],
}
result = await client.execute_query_json(body, include_total=True)
async for record in result.stream:
    # record has Contact fields + activeOpportunities (count)
    print(record.get("code"), record.get("activeOpportunities"))
total = result.total
```

### Custom query (JSON) — with relation filter and includeMeta

```python
body = {
    "document": "Contact",
    "fields": "code,name",
    "sort": [{"property": "name.full", "direction": "ASC"}],
    "limit": 1000,
    "includeMeta": True,
    "relations": [
        {
            "document": "Opportunity",
            "lookup": "contact",
            "filter": {"match": "and", "conditions": [{"term": "status", "operator": "in", "value": ["Nova", "Em Visitação"]}]},
            "aggregators": {"activeOpportunities": {"aggregator": "count"}},
        },
    ],
}
result = await client.execute_query_json(body, include_total=True, include_meta=True)
meta = result.meta  # document, relations, warnings, executionTimeMs, total
async for record in result.stream:
    print(record)
```

### Custom query (JSON) — Product + relation with push and count

From crossModuleQuery.integration.test (Product + ProductsPerOpportunities): aggregators push and count.

```python
body = {
    "document": "Product",
    "filter": {"match": "and", "conditions": [{"term": "_id", "operator": "equals", "value": "some-id"}]},
    "fields": "code,type",
    "limit": 1,
    "relations": [
        {
            "document": "ProductsPerOpportunities",
            "lookup": "product",
            "fields": "status,rating,contact",
            "sort": [{"property": "_createdAt", "direction": "DESC"}],
            "limit": 100,
            "aggregators": {
                "offers": {"aggregator": "push"},
                "offerCount": {"aggregator": "count"},
            },
        },
    ],
}
result = await client.execute_query_json(body)
async for record in result.stream:
    print(record.get("offers"), record.get("offerCount"))
```

### Custom query (SQL) — JOIN and GROUP BY

From queryApi.test: SELECT with INNER JOIN, GROUP BY, ORDER BY, LIMIT. Server returns NDJSON; first line can be _meta when includeMeta true.

```python
sql = """
SELECT ct.code, ct.name, COUNT(o._id) AS activeOpportunities
FROM Contact ct
INNER JOIN Opportunity o ON ct._id = o.contact._id
GROUP BY ct.code, ct.name
ORDER BY ct.name ASC
LIMIT 1000
"""
result = await client.execute_query_sql(sql, include_total=True, include_meta=True)
# X-Total-Count header and result.total when include_total=True
# result.meta when include_meta=True (document, relations, warnings, total)
async for record in result.stream:
    print(record.get("code"), record.get("activeOpportunities"))
```

### Custom query (SQL) — error handling

Empty SQL or non-SELECT returns 400 with _meta.success false and errors; SDK raises KonectyAPIError.

```python
from KonectySdkPython import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError

try:
    result = await client.execute_query_sql("")  # empty sql
except KonectyAPIError as e:
    # e.args[0] or errors list from server
    print("Validation errors:", e.args)
try:
    result = await client.execute_query_sql("DROP TABLE Contact")  # only SELECT allowed
except KonectyAPIError as e:
    print("SQL error:", e.args)  # e.g. "Only SELECT queries are allowed"
```

### KPI — count and sum

```python
from KonectySdkPython.lib.feature_types import KpiConfig

# Count (no field)
kpi_count = KpiConfig(operation="count")
r = await client.get_kpi("Opportunity", kpi_count, filter_params=filter_params)
print(r["value"], r["count"])

# Sum (field required)
kpi_sum = KpiConfig(operation="sum", field="value")
r = await client.get_kpi("Opportunity", kpi_sum, filter_params=filter_params)
```

### Comments — create and list

```python
# Create comment (optionally reply via parent_id)
await client.create_comment("Opportunity", opportunity_id, "Follow-up needed", parent_id=None)
# List comments
resp = await client.get_comments("Opportunity", opportunity_id)
comments = resp.get("data", [])
# Search users for @mention
users_resp = await client.search_comment_users("Opportunity", opportunity_id, query="john")
```

### Subscriptions and notifications

```python
# Subscribe to record
await client.subscribe("Opportunity", opportunity_id)
# Check status
status = await client.get_subscription_status("Opportunity", opportunity_id)
# Notifications
notifications = await client.list_notifications(read=False, page=1, limit=20)
count = await client.get_unread_notifications_count()
await client.mark_notification_read(notification_id)
await client.mark_all_notifications_read()
```

### Export list

```python
filter_params = KonectyFilter.create().add_condition("status", "equals", "Open")
csv_bytes = await client.export_list("Contact", "default", "csv", filter_params=filter_params, limit=1000)
with open("contacts.csv", "wb") as f:
    f.write(csv_bytes)
```

---

## 21. Quick reference table (KonectyClient methods)

| Method | Async | Returns |
|--------|--------|--------|
| find, find_sync | yes / no | List[KonectyDict] |
| find_one, find_one_sync | yes / no | Optional[KonectyDict] |
| find_by_id | yes | Optional[KonectyDict] |
| find_stream | yes | FindStreamResult (.stream, .total) |
| count_stream | yes | int |
| count_documents | yes | int |
| create | yes | Optional[KonectyDict] |
| update_one, update | yes | Optional[KonectyDict] / list |
| delete_one | yes | Optional[KonectyDict] |
| upload_file | yes | str (file key) |
| download_file, download_image | yes | bytes |
| export_list | yes | bytes |
| get_kpi, get_graph, get_pivot | yes | dict / str (SVG) / dict |
| get_comments, create_comment, update_comment, delete_comment | yes | dict |
| search_comment_users, search_comments | yes | dict |
| get_subscription_status, subscribe, unsubscribe | yes | dict |
| list_notifications, get_unread_notifications_count | yes | dict |
| mark_notification_read, mark_all_notifications_read | yes | dict |
| change_user_* (add, remove, define, replace, count_inactive, remove_inactive, set_queue) | yes | dict |
| execute_query_json, execute_query_sql | yes | QueryResult (.stream, .total, .meta) |
| list_saved_queries, get_saved_query, create_saved_query, update_saved_query, delete_saved_query, share_saved_query | yes | dict |
| get_document, get_schema | yes | Optional[KonectyDict] |
| get_setting, get_settings (and _sync) | yes / no | Optional[str] / Dict[str, str] |

Use this document as the single reference when implementing or reviewing code that depends on the Konecty SDK Python. Do not rely on external docs or other files; all usage, examples, and caveats are above.
