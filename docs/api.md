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

| Endpoint | Método | Propósito | Uso no SDK |
|----------|--------|-----------|------------|
| `/rest/data/{module}/find` | GET | Buscar registros com filtro, ordenação, paginação e projeção de campos. | `find`, `find_sync`, `count_documents` em client.py |
| `/rest/data/{module}/{id}` | GET | Obter um registro pelo identificador. | `find_by_id` em client.py |
| `/rest/data/{module}` | POST | Criar um novo registro. Corpo: objeto com os campos do documento. | `create` em client.py |
| `/rest/data/{module}` | PUT | Atualizar um ou mais registros. Corpo: objeto com `ids` (lista de `_id` e `_updatedAt`) e `data` (campos a atualizar). | `update_one`, `update` em client.py |
| `/rest/data/{module}` | DELETE | Excluir registros. Corpo: objeto com `ids` (lista de `_id` e `_updatedAt`). | `delete_one` em client.py |
| `/rest/menu/documents/{document_id}` | GET | Obter metadados do documento (schema/menu). | `get_document`, `get_schema` em client.py |
| `/rest/file/upload/ns/access/{module}/{record_code}/{field_name}` | POST | Upload de arquivo para um campo de um registro. Multipart/form-data. | FileManager e `upload_file` em client.py |

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

O corpo da requisição é um único objeto com os campos do documento. O SDK remove antes do envio os campos listados em `KONECTY_CREATE_IGNORE_FIELDS` (_updatedAt, _createdAt, _updatedBy, _createdBy). Datas são serializadas no formato `$date` em ISO8601.

## Atualização de registros (PUT)

O corpo contém:

- **ids:** lista de objetos com `_id` (identificador do registro) e `_updatedAt` (data da última atualização no formato Konecty `$date`). O Konecty usa isso para controle de concorrência.
- **data:** objeto com apenas os campos a serem atualizados.

O SDK não envia no `data` os campos em `KONECTY_UPDATE_IGNORE_FIELDS` (_id, code, _updatedAt, _createdAt, _updatedBy, _createdBy). O tipo `KonectyUpdateId` e `KonectyDateTime` em types.py garantem o formato correto.

## Exclusão (DELETE)

O corpo contém **ids:** lista de objetos com `_id` e `_updatedAt`, no mesmo formato da atualização. O SDK envia um único item em `delete_one`.

## Upload de arquivo (POST)

O endpoint utilizado pelo SDK é da forma `/rest/file/upload/ns/access/{module}/{record_code}/{field_name}` (segmentos codificados para URL). O Konecty também expõe rotas com namespace e accessId variáveis; o SDK usa o path com "ns" e "access" fixos. A requisição é multipart/form-data. O servidor pode impor tamanho máximo de arquivo (ex.: configuração de storage no namespace). A resposta de sucesso inclui um identificador do arquivo (key) que o SDK retorna.

## Outros endpoints do Konecty (não utilizados pelo SDK)

O Konecty expõe ainda, entre outros:

- **Stream:** GET `/rest/stream/{document}/find` e GET `/rest/stream/{document}/findStream` para find em modo stream (resposta em streaming); GET `/rest/stream/{document}/count` para contagem. Parâmetros de query análogos ao find (filter, sort, limit, start, fields, etc.). findStream pode retornar header `X-Total-Count` quando solicitado.
- **Menu:** GET `/rest/menu/list`, GET `/rest/menu/documents` para lista de documentos.
- **Data:** lookup (`/rest/data/{document}/lookup/{field}`), history, relations, export (list por tipo csv/xlsx/json), pivot, graph, queue, lead/save.
- **File:** download, delete, image, watermark.
- **Auth, health, notifications, subscriptions, process, etc.**

O SDK atualmente não implementa chamadas a esses endpoints; a documentação aqui limita-se ao que o SDK usa e ao formato geral da API.
