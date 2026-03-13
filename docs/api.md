# API Konecty utilizada pelo SDK

Este documento descreve a API REST do Konecty que o SDK Python utiliza. A referência é o código-fonte do Konecty e a collection Postman quando disponível.

## Base URL e autenticação

- **Base URL:** Configurável via variável de ambiente `KONECTY_URL`. Valor padrão: `http://localhost:3000`.
- **Autenticação:** O SDK envia o token no header `Authorization`. O valor do token é definido pela variável de ambiente `KONECTY_TOKEN`. O header é enviado literalmente (sem prefixo "Bearer") em todas as requisições.

## Formato de resposta padrão

As respostas da API Konecty seguem um formato comum:

- **success:** booleano indicando se a operação foi bem-sucedida.
- **data:** payload da resposta (lista de registros, objeto criado/atualizado, etc.).
- **errors:** presente em caso de falha; lista de objetos com informações de erro.

Quando `success` é falso, o SDK converte a resposta em exceção `KonectyAPIError` com os erros retornados.

## Endpoints utilizados pelo SDK

| Endpoint                                                          | Método | Propósito                                                                                                              | Uso no SDK                                          |
| ----------------------------------------------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| `/rest/data/{module}/find`                                        | GET    | Buscar registros com filtro, ordenação, paginação e projeção de campos.                                                | `find`, `find_sync`, `count_documents` em client.py |
| `/rest/data/{module}/{id}`                                        | GET    | Obter um registro pelo identificador.                                                                                  | `find_by_id` em client.py                           |
| `/rest/data/{module}`                                             | POST   | Criar um novo registro. Corpo: objeto com os campos do documento.                                                      | `create` em client.py                               |
| `/rest/data/{module}`                                             | PUT    | Atualizar um ou mais registros. Corpo: objeto com `ids` (lista de `_id` e `_updatedAt`) e `data` (campos a atualizar). | `update_one`, `update` em client.py                 |
| `/rest/data/{module}`                                             | DELETE | Excluir registros. Corpo: objeto com `ids` (lista de `_id` e `_updatedAt`).                                            | `delete_one` em client.py                           |
| `/rest/menu/documents/{document_id}`                              | GET    | Obter metadados do documento (schema/menu).                                                                            | `get_document`, `get_schema` em client.py           |
| `/rest/file/upload/ns/access/{module}/{record_code}/{field_name}` | POST   | Upload de arquivo para um campo de um registro. Multipart/form-data.                                                   | FileManager e `upload_file` em client.py            |

O parâmetro `module` (ou `document`) identifica o tipo de documento no Konecty (ex.: Contact, User, Setting).

## Parâmetros do find (GET /rest/data/{module}/find)

Os parâmetros são enviados como query string. O SDK monta esses parâmetros a partir de `KonectyFindParams` e `KonectyFilter` (módulo filters).

- **filter:** objeto de filtro em JSON (match, conditions, filters aninhados). No Konecty o filtro usa estrutura com `match` (and/or), `conditions` (term, operator, value, disabled) e `filters` para filtros aninhados. O SDK serializa o filtro com `json_serial` (datas no formato `$date` ISO8601).
- **start:** índice inicial para paginação (skip).
- **limit:** quantidade máxima de registros.
- **sort:** ordenação, em geral array JSON de objetos com propriedade e direção (ASC/DESC).
- **fields:** lista de nomes de campos a retornar; no SDK é enviada como string separada por vírgula.

A API do Konecty aceita ainda parâmetros opcionais como `displayName`, `displayType` e `withDetailFields`; o SDK atual não os expõe diretamente nos métodos de find.

## Formato de filtro (Konecty)

O filtro segue o modelo do Konecty (Filter/KonFilter): `match` (and ou or), `conditions` (array de condições com term, operator, value, disabled) e `filters` (array de filtros aninhados com a mesma estrutura). Operadores típicos incluem equals, not_equals, in, not_in, less_than, greater_than, between, exists, etc., alinhados ao enum `FilterOperator` no SDK.

## Criação de registros (POST)

O corpo da requisição é um único objeto com os campos do documento. O SDK remove antes do envio os campos listados em `KONECTY_CREATE_IGNORE_FIELDS` (\_updatedAt, \_createdAt, \_updatedBy, \_createdBy). Datas são serializadas no formato `$date` em ISO8601.

## Atualização de registros (PUT)

O corpo contém:

- **ids:** lista de objetos com `_id` (identificador do registro) e `_updatedAt` (data da última atualização no formato Konecty `$date`). O Konecty usa isso para controle de concorrência.
- **data:** objeto com apenas os campos a serem atualizados.

O SDK não envia no `data` os campos em `KONECTY_UPDATE_IGNORE_FIELDS` (\_id, code, \_updatedAt, \_createdAt, \_updatedBy, \_createdBy). O tipo `KonectyUpdateId` e `KonectyDateTime` em types.py garantem o formato correto.

## Exclusão (DELETE)

O corpo contém **ids:** lista de objetos com `_id` e `_updatedAt`, no mesmo formato da atualização. O SDK envia um único item em `delete_one`.

## Upload de arquivo (POST)

O endpoint utilizado pelo SDK é da forma `/rest/file/upload/ns/access/{module}/{record_code}/{field_name}` (segmentos codificados para URL). O Konecty também expõe rotas com namespace e accessId variáveis; o SDK usa o path com "ns" e "access" fixos. A requisição é multipart/form-data. O servidor pode impor tamanho máximo de arquivo (ex.: configuração de storage no namespace). A resposta de sucesso inclui um identificador do arquivo (key) que o SDK retorna.

## Endpoints adicionais utilizados pelo SDK (stream, arquivos, agregação, comentários, etc.)

O SDK utiliza também os seguintes endpoints, expostos como métodos no `KonectyClient`:

| Endpoint                                                                                           | Método          | Uso no SDK                                                                                                                         |
| -------------------------------------------------------------------------------------------------- | --------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `/rest/stream/{module}/findStream`                                                                 | GET             | `find_stream` — stream NDJSON; parâmetros análogos ao find; header `X-Total-Count` quando solicitado.                              |
| `/rest/stream/{module}/count`                                                                      | GET             | `count_stream` — contagem; parâmetros filter, displayName, displayType, sort, withDetailFields.                                    |
| `/rest/file/{module}/{code}/{field}/{fileName}`                                                    | GET             | `download_file` — retorno em bytes.                                                                                                |
| `/rest/image/{module}/{recordId}/{field}/{fileName}` ou `.../{style}/...` (style: full, thumb, wm) | GET             | `download_image` — retorno em bytes.                                                                                               |
| `/rest/data/{module}/list/{listName}/{type}`                                                       | GET             | `export_list` — type csv, xlsx ou json; retorno em bytes. Parâmetros filter, sort, fields, start, limit, displayName, displayType. |
| `/rest/data/{module}/kpi`                                                                          | GET             | `get_kpi` — query `kpiConfig` (JSON), filter, etc. Resposta: success, value, count.                                                |
| `/rest/data/{module}/graph`                                                                        | GET             | `get_graph` — query `graphConfig` (JSON), filter, etc. Resposta: corpo SVG.                                                        |
| `/rest/data/{module}/pivot`                                                                        | GET             | `get_pivot` — query `pivotConfig` (JSON), filter, etc. Resposta JSON.                                                              |
| `/rest/comment/{module}/{dataId}`                                                                  | GET/POST        | `get_comments`, `create_comment`. POST: body text, parentId opcional.                                                              |
| `/rest/comment/{module}/{dataId}/{commentId}`                                                      | PUT/DELETE      | `update_comment`, `delete_comment`.                                                                                                |
| `/rest/comment/{module}/{dataId}/users/search`                                                     | GET             | `search_comment_users` — query q.                                                                                                  |
| `/rest/comment/{module}/{dataId}/search`                                                           | GET             | `search_comments` — query q, authorId, startDate, endDate, page, limit.                                                            |
| `/rest/subscriptions/{module}/{dataId}`                                                            | GET/POST/DELETE | `get_subscription_status`, `subscribe`, `unsubscribe`.                                                                             |
| `/rest/notifications`                                                                              | GET             | `list_notifications` — query read, page, limit.                                                                                    |
| `/rest/notifications/unread-count`                                                                 | GET             | `get_unread_notifications_count`.                                                                                                  |
| `/rest/notifications/{id}/read`                                                                    | PUT             | `mark_notification_read`.                                                                                                          |
| `/rest/notifications/read-all`                                                                     | PUT             | `mark_all_notifications_read`.                                                                                                     |
| `/rest/changeUser/{module}/add` (remove, define, replace, countInactive, removeInactive, setQueue) | POST            | `change_user_add`, `change_user_remove`, etc. — body ids e, quando aplicável, data.                                                |
| `/rest/query/saved`                                                                                | GET/POST        | `list_saved_queries`, `create_saved_query`. POST: name, query (CrossModuleQuery), description opcional.                            |
| `/rest/query/saved/{id}`                                                                           | GET/PUT/DELETE  | `get_saved_query`, `update_saved_query`, `delete_saved_query`.                                                                     |
| `/rest/query/saved/{id}/share`                                                                     | PATCH           | `share_saved_query` — body sharedWith (array), isPublic opcional.                                                                  |

## Query customizada (JSON e SQL)

Além das consultas salvas, o Konecty expõe execução direta de consultas cross-module via dois endpoints. O SDK oferece `execute_query_json` e `execute_query_sql`; ambos retornam um objeto com stream (gerador assíncrono de registros), total (quando solicitado) e meta (quando solicitado).

### POST /rest/query/json

- **Corpo:** Objeto CrossModuleQuery: document (obrigatório), filter, fields, sort, limit (default 1000, máx. 100_000), start (default 0), relations (array, máx. 10), groupBy, aggregators, includeTotal (default true), includeMeta (default false). Cada relação: document, lookup, on (left/right opcional), filter, fields, sort, limit, start, aggregators (obrigatório, pelo menos um por relação), relations (aninhadas, máx. 10, profundidade máx. 2). Constantes do servidor: MAX_RELATIONS=10, MAX_NESTING_DEPTH=2, MAX_RELATION_LIMIT=100_000.
- **Resposta:** Content-Type application/x-ndjson. Primeira linha pode ser um objeto com chave \_meta (quando includeMeta é true), contendo success, document, relations, warnings, executionTimeMs, total. As demais linhas são um objeto JSON por registro. Header X-Total-Count quando includeTotal.
- **Erro:** Em falha o servidor pode retornar status 400 ou 500; o corpo em NDJSON contém uma linha com \_meta e success false e lista errors. O SDK converte em KonectyAPIError.

### POST /rest/query/sql

- **Corpo:** Objeto com sql (string obrigatória), includeTotal (boolean, default true), includeMeta (boolean, default false). O servidor converte a SQL em CrossModuleQuery (parser estilo MySQL; apenas SELECT; comprimento máximo 10_000 caracteres) e executa pelo mesmo motor.
- **Resposta:** Mesmo formato NDJSON e header X-Total-Count que query/json.
- **Erro:** SQL inválida ou erro de parse retornam 400 com linha NDJSON \_meta e success false e errors (ex.: mensagem SqlParseError). O SDK converte em KonectyAPIError.

### Uso e caveats

- Quando usar JSON: controle fino da estrutura CrossModuleQuery (relations, aggregators, groupBy). Quando usar SQL: consultas ad-hoc em linguagem familiar; sujeito a limites de comprimento e dialeto (apenas SELECT).
- Limites do servidor: MAX_RELATIONS, MAX_NESTING_DEPTH, MAX_RELATION_LIMIT; para SQL, comprimento máximo 10_000 caracteres.
- Permissões: aplicadas por documento; falhas de acesso podem aparecer em warnings na meta ou em erros.
- O stream retornado pelo SDK é um gerador assíncrono; consumir uma única vez; total e meta ficam disponíveis no objeto resultado (total também no header X-Total-Count).
- **Criador tipado:** O SDK expõe em `lib.feature_types.query_json` classes/dataclasses fortemente tipadas para montar o corpo da query sem builder: `QueryJson`, `QueryRelation`, `QueryFilter`, `QueryFilterCondition`, `QuerySortItem`, `AggregatorSpec`, `ExplicitJoinCondition`. Use propriedades para preencher e chame `to_dict()` no `QueryJson` (ou passe a instância diretamente para `execute_query_json`, que aceita objetos com `to_dict()` ou `model_dump()`). Tipos Literal para `AggregatorName`, `FilterMatch`, `SortDirection` garantem intellisense alinhado ao schema do Konecty.

## Outros endpoints do Konecty (não utilizados pelo SDK)

O Konecty expõe ainda, entre outros: Menu (list, documents), Data (lookup, history, relations, queue, lead/save), File (delete), Auth, health, process, etc. A documentação acima cobre o que o SDK utiliza e o contrato da query customizada.
