# Implementação das features do plano (stream, files, export, KPI, graph, pivot, comments, subscriptions, notifications, change user, query customizada, saved queries)

## Resumo

Implementação completa do plano de features do SDK: novo módulo HTTP interno, serviços por domínio (stream, files, export, aggregation, comments, subscriptions, notifications, change_user, query), tipos em lib.feature_types (KPI, CrossModuleQuery), e métodos no KonectyClient para todas as funcionalidades descritas em docs/features-candidatas-sdk.md. Documentação da API (api.md) e da query customizada (JSON e SQL) atualizadas; skill do agente e reference.md atualizados.

## Motivação

Expor no SDK Python as capacidades da API Konecty já existentes (find stream, count stream, download de arquivo/imagem, export de listas, KPI, graph, pivot, comentários, inscrições, notificações, change user, execução de query customizada e CRUD de consultas salvas) com API unificada no KonectyClient e documentação alinhada ao contrato real.

## O que mudou

- **lib/exceptions.py** — Novo módulo com KonectyError, KonectyAPIError, KonectyValidationError, KonectySerializationError (extraídos do client para evitar import circular).
- **lib/http.py** — Novo módulo com `request(client, method, path, ...)` e `StreamResponse` para respostas em stream ou bytes; usado por client e serviços.
- **lib/services/** — Novo pacote com BaseService e serviços: stream (find_stream, count_stream), files (download_file, download_image), export (export_list), aggregation (get_kpi, get_graph, get_pivot), comments, subscriptions, notifications, change_user, query (execute_query_json, execute_query_sql, saved queries CRUD).
- **lib/feature_types/** — Novo pacote com kpi (KpiConfig, KpiOperation) e cross_module_query (CrossModuleQuery, CrossModuleRelation, Aggregator, constantes).
- **KonectyClient** — Novo método interno `_request`; propriedades privadas para cada serviço; métodos públicos: find_stream, count_stream, download_file, download_image, export_list, get_kpi, get_graph, get_pivot, get_comments, create_comment, update_comment, delete_comment, search_comment_users, search_comments, get_subscription_status, subscribe, unsubscribe, list_notifications, get_unread_notifications_count, mark_notification_read, mark_all_notifications_read, change_user_* (add, remove, define, replace, count_inactive, remove_inactive, set_queue), execute_query_json, execute_query_sql, list_saved_queries, get_saved_query, create_saved_query, update_saved_query, delete_saved_query, share_saved_query.
- **docs/api.md** — Nova seção de endpoints adicionais utilizados pelo SDK e subseção "Query customizada (JSON e SQL)" com descrição do contrato (CrossModuleQuery, SQL, NDJSON, _meta, X-Total-Count, erros).
- **.cursor/skills/konecty-sdk-python/** — SKILL.md e reference.md atualizados com todos os novos métodos e tipos.

## Impacto técnico

- Compatibilidade retroativa mantida: métodos e imports existentes inalterados; novos métodos e módulos são aditivos.
- Quem depender do SDK pode passar a usar find_stream, download_file, get_kpi, execute_query_json/sql, etc., sem alterar código já escrito.

## Impacto externo

- Usuários do SDK podem integrar stream, export, agregações, comentários, notificações, change user e query customizada a partir da mesma instância do KonectyClient.

## Como validar

- Executar testes existentes (se houver).
- Chamar os novos métodos contra uma instância Konecty (ex.: find_stream com KonectyFindParams, execute_query_sql com uma SELECT simples, get_kpi com KpiConfig(operation="count")).

## Arquivos afetados

- KonectySdkPython/lib/exceptions.py (novo)
- KonectySdkPython/lib/http.py (novo)
- KonectySdkPython/lib/client.py (alterado)
- KonectySdkPython/lib/services/ (novo: base, stream, files, export, aggregation, comments, subscriptions, notifications, change_user, query)
- KonectySdkPython/lib/feature_types/ (novo: kpi, cross_module_query)
- docs/api.md
- docs/changelog/2025-03-13_implementacao-features-sdk.md
- docs/changelog/README.md
- .cursor/skills/konecty-sdk-python/SKILL.md
- .cursor/skills/konecty-sdk-python/reference.md

## Existe migração?

Não. Nenhuma alteração quebrante; apenas adições de API e módulos internos.
