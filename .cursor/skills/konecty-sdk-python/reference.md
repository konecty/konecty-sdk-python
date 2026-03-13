# Konecty SDK Python — Quick reference

Use this file when you need a compact list of exports or pointers to project docs.

## Public exports (from KonectySdkPython)

| Symbol | Origin | Purpose |
|--------|--------|---------|
| KonectyClient | lib.client | REST client for Konecty API |
| KonectyDict | lib.client | Type alias Dict[str, Any] for records |
| KonectyFilter | lib.client (from filters) | Filter builder for find (match, conditions, filters) |
| KonectyFindParams | lib.client (from filters) | find params: filter, start, limit, sort, fields |
| FileManager | lib.file_manager | File upload (used by client.upload_file) |
| KonectyModelGenerator | lib.model | Generate Pydantic models from document schema |
| fill_settings, fill_settings_sync | lib.settings | Populate a Pydantic settings class from env + Konecty Setting module |
| KonectyAddress | lib.types (as Address) | Address model |
| KonectyBaseModel | lib.types | Base model for Konecty documents |
| KonectyDateTime | lib.types | Date in Konecty $date format |
| KonectyEmail | lib.types | Email field |
| KonectyLabel | lib.types | Label (e.g. pt_BR, en) |
| KonectyLookup | lib.types | Lookup reference (_id) |
| KonectyPersonName | lib.types | Person name (first, last, full) |
| KonectyPhone | lib.types | Phone (countryCode, phoneNumber, type) |
| KonectyUser | lib.types | User ref (id, name, active) |
| apply_command, backup_command, pull_command | cli | CLI command handlers |

From **KonectySdkPython.lib.types** only: KonectyUpdateId (for update/delete ids). From **KonectySdkPython.lib.filters**: FilterOperator, FilterMatch, SortOrder, SortDirection, FilterCondition. From **KonectySdkPython.lib.client**: KonectyError, KonectyAPIError, KonectyValidationError, FindStreamResult. From **KonectySdkPython.lib.services.query**: QueryResult. From **KonectySdkPython.lib.feature_types**: KpiConfig, KpiOperation, CrossModuleQuery, CrossModuleRelation, Aggregator (and constants MAX_RELATIONS, MAX_RELATION_LIMIT, DEFAULT_PRIMARY_LIMIT).

## KonectyClient methods (summary)

| Method | Async | Args | Returns |
|--------|--------|------|--------|
| find | yes | module, KonectyFindParams | List[KonectyDict] |
| find_sync | no | module, KonectyFindParams | List[KonectyDict] |
| find_one | yes | module, KonectyFilter | Optional[KonectyDict] |
| find_one_sync | no | module, KonectyFilter | Optional[KonectyDict] |
| find_by_id | yes | module, id | Optional[KonectyDict] |
| find_stream | yes | module, KonectyFindParams, include_total? | FindStreamResult (.stream, .total) |
| count_stream | yes | module, filter_params?, **kwargs | int |
| download_file | yes | module, record_code, field_name, file_name | bytes |
| download_image | yes | module, record_id, field_name, file_name, style? | bytes |
| export_list | yes | module, list_name, format, filter_params?, **kwargs | bytes |
| get_kpi | yes | module, KpiConfig, filter_params?, **kwargs | dict (value, count) |
| get_graph | yes | module, graph_config, filter_params?, **kwargs | str (SVG) |
| get_pivot | yes | module, pivot_config, filter_params?, **kwargs | dict |
| get_comments | yes | module, data_id | dict |
| create_comment | yes | module, data_id, text, parent_id? | dict |
| update_comment | yes | module, data_id, comment_id, text | dict |
| delete_comment | yes | module, data_id, comment_id | dict |
| search_comment_users | yes | module, data_id, query? | dict |
| search_comments | yes | module, data_id, query?, author_id?, ... | dict |
| get_subscription_status | yes | module, data_id | dict |
| subscribe | yes | module, data_id | dict |
| unsubscribe | yes | module, data_id | dict |
| list_notifications | yes | read?, page?, limit? | dict |
| get_unread_notifications_count | yes | | dict |
| mark_notification_read | yes | notification_id | dict |
| mark_all_notifications_read | yes | | dict |
| change_user_add | yes | module, ids, users | dict |
| change_user_remove | yes | module, ids, users | dict |
| change_user_define | yes | module, ids, users | dict |
| change_user_replace | yes | module, ids, from_user?, to_user? | dict |
| change_user_count_inactive | yes | module, ids | dict |
| change_user_remove_inactive | yes | module, ids | dict |
| change_user_set_queue | yes | module, ids, queue | dict |
| execute_query_json | yes | body, include_total?, include_meta? | QueryResult (.stream, .total, .meta) |
| execute_query_sql | yes | sql, include_total?, include_meta? | QueryResult |
| list_saved_queries | yes | | dict |
| get_saved_query | yes | query_id | dict |
| create_saved_query | yes | name, query, description? | dict |
| update_saved_query | yes | query_id, name?, description?, query? | dict |
| delete_saved_query | yes | query_id | dict |
| share_saved_query | yes | query_id, shared_with, is_public? | dict |
| create | yes | module, KonectyDict | Optional[KonectyDict] |
| update_one | yes | module, id, updatedAt, data | Optional[KonectyDict] |
| update | yes | module, ids, data | list[KonectyDict] |
| delete_one | yes | module, id, updatedAt | Optional[KonectyDict] |
| get_document | yes | document_id | Optional[KonectyDict] |
| get_schema | yes | document_id | Optional[KonectyDict] |
| get_setting | yes | key | Optional[str] |
| get_setting_sync | no | key | Optional[str] |
| get_settings | yes | keys: List[str] | Dict[str, str] |
| get_settings_sync | no | keys: List[str] | Dict[str, str] |
| count_documents | yes | module, KonectyFilter | int |
| upload_file | yes | module, record_code, field_name, file, file_name?, file_type? | str (file key) |

## Project documentation

- **docs/README.md** — Index of documentation.
- **docs/api.md** — Konecty REST endpoints used by the SDK, request/response format, filter format.
- **docs/development.md** — Environment, package structure, build, env vars.

Read those files when you need endpoint-level details or contribution instructions.
