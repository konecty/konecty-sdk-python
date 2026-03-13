---
name: konecty-sdk-python
description: >-
    Teaches the agent how to use the Konecty SDK Python (client, filters, types,
    settings, CLI) for the Konecty CRM REST API. Use when the project depends on
    konecty-sdk-python or konecty_sdk_python, when the user asks about Konecty
    API integration, CRUD with Konecty, find/filter records, upload files to
    Konecty, or konecty-cli commands.
---

# Konecty SDK Python — Agent Skill

This skill summarizes the Konecty SDK Python so the agent can correctly use its APIs, types, and CLI in projects that depend on it.

## What the SDK provides

- **REST client** for the [Konecty](https://github.com/konecty/Konecty) CRM API: find, get by id, create, update, delete, get document/schema, get settings, count, file upload; plus find_stream, count_stream, download_file, download_image, export_list, get_kpi, get_graph, get_pivot, comments, subscriptions, notifications, change_user, execute_query_json, execute_query_sql, saved queries (list/get/create/update/delete/share).
- **CLI** `konecty-cli`: apply, backup, pull (metadata operations against MongoDB; not a substitute for the REST client).
- **Types and filters**: Pydantic models for Konecty data (datetime, lookup, phone, email, etc.) and filter/sort builders for find queries. Feature types: KpiConfig, CrossModuleQuery/CrossModuleRelation (lib.feature_types).

## Environment

Projects must set (or the client is built with explicit values):

- **KONECTY_URL** — Base URL of the Konecty API (default `http://localhost:3000`).
- **KONECTY_TOKEN** — Token sent in the `Authorization` header (no "Bearer" prefix).

## Main imports (public API)

From package root:

- `KonectyClient`, `KonectyDict`, `KonectyFilter`, `KonectyFindParams`
- `FileManager`
- `KonectyModelGenerator`
- `fill_settings`, `fill_settings_sync`
- Types: `KonectyAddress`, `KonectyBaseModel`, `KonectyDateTime`, `KonectyEmail`, `KonectyLabel`, `KonectyLookup`, `KonectyPersonName`, `KonectyPhone`, `KonectyUser`
- CLI (if needed): `apply_command`, `backup_command`, `pull_command`

From `KonectySdkPython.lib` the same symbols are available; from `KonectySdkPython.lib.types` also `KonectyUpdateId`. From `KonectySdkPython.lib.filters`: `FilterOperator`, `FilterMatch`, `SortOrder`, `SortDirection`, `FilterCondition` for building filters by hand. Exceptions: `KonectyError`, `KonectyAPIError`, `KonectyValidationError` (from client module).

## KonectyClient usage

- **Constructor:** `KonectyClient(base_url: str, token: str)`. Use env or config for base_url and token.
- **Find (async):** `find(module: str, options: KonectyFindParams) -> List[KonectyDict]`. Use `KonectyFindParams(filter=..., start=..., limit=..., sort=..., fields=...)`.
- **Find (sync):** `find_sync(module, options)` — same contract, blocking.
- **Find one:** `find_one(module, filter_params)` async; `find_one_sync(module, filter_params)` sync. Both return one record or None.
- **By ID:** `find_by_id(module: str, id: str) -> Optional[KonectyDict]`.
- **Create:** `create(module: str, data: KonectyDict) -> Optional[KonectyDict]`. Do not send \_createdAt, \_updatedAt, \_createdBy, \_updatedBy; SDK strips them.
- **Update one:** `update_one(module, id, updatedAt: datetime, data: KonectyDict)`. Requires current \_updatedAt for concurrency.
- **Update many:** `update(module, ids: list[KonectyUpdateId], data: KonectyDict) -> list[KonectyDict]`. Each id is dict with \_id and \_updatedAt (use `KonectyUpdateId.from_dict`).
- **Delete:** `delete_one(module, id, updatedAt: datetime)`.
- **Document/schema:** `get_document(document_id)`, `get_schema(document_id)` — return metadata for a document type.
- **Settings:** `get_setting(key)`, `get_settings(keys)` async; `get_setting_sync(key)`, `get_settings_sync(keys)` sync. They query the Setting module.
- **Count:** `count_documents(module, filter_params: KonectyFilter) -> int`.
- **Upload file:** `upload_file(module, record_code, field_name, file, file_name=None, file_type=None) -> str`. `file` can be bytes, URL string, or AsyncGenerator[bytes, None]. Returns file key from Konecty.
- **Stream:** `find_stream(module, options: KonectyFindParams, include_total=False) -> FindStreamResult`. Result has `.stream` (async generator of dicts) and `.total` (int or None). Consume with `async for record in result.stream`.
- **Stream count:** `count_stream(module, filter_params=None, **kwargs) -> int`. GET /rest/stream/{module}/count.
- **Download file/image:** `download_file(module, record_code, field_name, file_name) -> bytes`; `download_image(module, record_id, field_name, file_name, style=None)` with style in full, thumb, wm. Returns bytes.
- **Export:** `export_list(module, list_name, format, filter_params=None, ...) -> bytes`. format: csv, xlsx, json, xls.
- **KPI:** `get_kpi(module, kpi_config: KpiConfig, filter_params=None, ...) -> dict` with value and count. KpiConfig from lib.feature_types (operation: count, sum, avg, min, max, countDistinct; field required for countDistinct).
- **Graph:** `get_graph(module, graph_config, filter_params=None, ...) -> str` (SVG). graph_config: type, xAxis, yAxis, series, etc. (dict or Pydantic).
- **Pivot:** `get_pivot(module, pivot_config, filter_params=None, ...) -> dict`. pivot_config: rows, columns, values.
- **Comments:** `get_comments(module, data_id)`, `create_comment(module, data_id, text, parent_id=None)`, `update_comment`, `delete_comment`, `search_comment_users(module, data_id, query)`, `search_comments(module, data_id, query=..., author_id=..., ...)`.
- **Subscriptions:** `get_subscription_status(module, data_id)`, `subscribe(module, data_id)`, `unsubscribe(module, data_id)`.
- **Notifications:** `list_notifications(read=..., page=..., limit=...)`, `get_unread_notifications_count()`, `mark_notification_read(notification_id)`, `mark_all_notifications_read()`.
- **Change user:** `change_user_add(module, ids, users)`, `change_user_remove`, `change_user_define`, `change_user_replace(module, ids, from_user=..., to_user=...)`, `change_user_count_inactive`, `change_user_remove_inactive`, `change_user_set_queue(module, ids, queue)`.
- **Query customizada:** `execute_query_json(body, include_total=True, include_meta=False) -> QueryResult`. body: dict, CrossModuleQuery (Pydantic), ou **QueryJson** (criador tipado em lib.feature_types.query_json). O criador tipado usa classes/dataclasses com props (sem builder): `QueryJson`, `QueryRelation`, `QueryFilter`, `QueryFilterCondition`, `QuerySortItem`, `AggregatorSpec`, `ExplicitJoinCondition`; tipos `AggregatorName`, `FilterMatch`, `SortDirection`. Instancie com propriedades e chame `.to_dict()` no QueryJson (ou passe a instância diretamente; o client aceita objetos com `to_dict()` ou `model_dump()`). `execute_query_sql(sql, ...) -> QueryResult`. QueryResult: `.stream`, `.total`, `.meta`. Resposta NDJSON; SQL: apenas SELECT, máx. 10_000 caracteres.
- **Saved queries:** `list_saved_queries()`, `get_saved_query(id)`, `create_saved_query(name, query, description=None)`, `update_saved_query(id, name=..., description=..., query=...)`, `delete_saved_query(id)`, `share_saved_query(id, shared_with, is_public=None)`.

All async methods use aiohttp; sync find uses requests. On API failure the client raises `KonectyAPIError` with the errors list from the response.

## Building find options

- **Filter:** `KonectyFilter.create(match="and"|"or")` then `.add_condition(term, operator, value)` and optionally `.add_filter(match)` for nested filters. Operator values: equals, not_equals, in, not_in, less_than, greater_than, less_or_equals, greater_or_equals, between, exists, contains, starts_with, end_with, not_contains (use `FilterOperator` enum or lowercase strings).
- **Sort:** `KonectyFindParams(..., sort=[SortOrder(property="fieldName", direction=SortDirection.DESC)], ...)`.
- **Pagination:** `start` and `limit` on `KonectyFindParams`. **Fields:** `fields` as list of field names (e.g. `["_id", "name"]`).

Example flow: build `KonectyFilter`, wrap in `KonectyFindParams(filter=..., limit=10)`, call `client.find(module, options)` or `client.find_sync(module, options)`.

## Types and update payloads

- **KonectyDateTime:** Konecty format `{"$date": "ISO8601"}`. Use `KonectyDateTime.from_datetime(dt)` and `.to_json()` for update/delete payloads.
- **KonectyUpdateId:** For update/delete, use `KonectyUpdateId.from_dict({"_id": id, "_updatedAt": ...})` or build from record after find; `.to_dict()` for request body.
- **KonectyBaseModel:** Base for document models; `to_dict()`, `to_update_dict()`, `from_dict()`, `from_json()`.
- **KonectyPhone**, **KonectyEmail**, **KonectyPersonName**, **KonectyLookup**, **Address:** Use for type-safe field values when building or parsing Konecty records.

## Settings from Konecty

- **fill_settings(settings_class)** (async) and **fill_settings_sync(settings_class)**: Given a Pydantic BaseModel class whose field names match Konecty Setting keys (or env vars in uppercase), fill an instance from env first, then from Konecty get_settings for the rest. Useful for config objects that live in Konecty or env.

## CLI (konecty-cli)

- **apply** — Apply metadata (e.g. from a directory) to MongoDB. Requires `--mongo-url` and `--database` (and optionally metadata path).
- **backup** — Backup metadata from MongoDB.
- **pull** — Pull metadata from Konecty (API) or MongoDB. Uses `--mongo-url`, `--database`; for API, Konecty URL and token must be configured.

CLI operates on the metadata database (MongoDB), not on the REST data API. For CRUD on business data, use KonectyClient.

## API endpoints (reference)

The client uses the Konecty REST endpoints documented in `docs/api.md`, including stream (findStream, count), file/image download, export (list), kpi, graph, pivot, comment, subscription, notification, changeUser, query/json, query/sql, and query/saved. Responses use `success`, `data`, and `errors` where applicable; stream endpoints return NDJSON. Query custom (JSON/SQL) is described in detail in api.md (CrossModuleQuery schema, SQL limits, NDJSON format, \_meta, X-Total-Count).

## Common pitfalls

- **Authorization:** Send the token as-is in the Authorization header; the SDK does not add "Bearer". Configure the same token Konecty expects (e.g. from login or API key).
- **Update/delete:** Always pass the current `_updatedAt` of the record; Konecty uses it for optimistic concurrency. After a find, use the same record’s \_updatedAt for update_one or delete_one.
- **Module name:** The `module` parameter is the Konecty document name (e.g. Contact, User, Setting), not a URL path. Get document names from the app or from get_document/get_schema.
- **Filter serialization:** Datetimes in filters must be serializable to Konecty format; the client uses a json_serial that emits `$date` for datetime. Use KonectyFilter/KonectyFindParams so the SDK serializes correctly.

## Additional resources

- **reference.md** (in this skill folder): Table of public exports and KonectyClient method summary.
- In the SDK repo: **docs/api.md** (API contract), **docs/development.md** (structure, build, env). Use them when you need endpoint details or contribution steps.

---

## Maintainers: keeping the skill updated

When you change the SDK code, keep this skill in sync so the agent continues to reflect the real API.

- **New or removed public exports** (in `KonectySdkPython/__init__.py` or `KonectySdkPython/lib/__init__.py`): Update the "Main imports" section in this file and the exports table in **reference.md**.
- **New, removed, or changed methods on KonectyClient or other public types:** Update the usage sections in this file and the method table in **reference.md**.
- **New endpoints, env vars, or CLI commands:** Update the relevant sections here and in **docs/api.md** or **docs/development.md** as applicable.
- **Changed behavior** (e.g. request/response format, error handling): Adjust the descriptions and "Common pitfalls" so the skill stays accurate.

Treat skill updates as part of the same change: when you modify the public surface of the SDK, update this skill (and reference.md) in the same commit or PR. See **docs/README.md** and **docs/development.md** for the project’s documentation and skill sync policy.
