# Criador de query tipado para query/json

## Resumo

Introduzido módulo de criador de query fortemente tipado para `POST /rest/query/json`, usando classes e dataclasses (sem paradigma builder), com intellisense alinhado ao schema do Konecty.

## Motivação

Permitir montar o corpo da consulta cross-module com tipos explícitos (Literal para aggregator, match, direction) e propriedades nomeadas, em vez de dicionários ou builder fluente.

## O que mudou

- **Novo módulo** `lib/feature_types/query_json.py`:
  - `QueryFilterCondition`: term, operator, value (opcional), editable, disabled, sort.
  - `QueryFilter`: match ("and"|"or"), conditions, text_search, filters (aninhados).
  - `QuerySortItem`: property, direction ("ASC"|"DESC").
  - `ExplicitJoinCondition`: left, right.
  - `AggregatorSpec`: aggregator (Literal com todos os nomes Konecty), field (opcional).
  - `QueryRelation`: document, lookup, aggregators (obrigatório), on, filter, fields, sort, limit, start, relations (aninhadas).
  - `QueryJson`: document, filter, fields, sort, limit, start, relations, group_by, aggregators, include_total, include_meta.
  - Tipos Literal: `AggregatorName`, `FilterMatch`, `SortDirection`; tipo `ConditionValue`.
  - Método `to_dict()` em cada classe para serializar ao payload da API (camelCase: includeTotal, includeMeta, groupBy, textSearch).
- **Integração:** `execute_query_json` aceita corpo com `to_dict()` (além de `model_dump()` e dict). Export em `lib.feature_types` de todos os tipos do criador.
- **Documentação:** `docs/api.md` descreve o criador tipado; skill e reference atualizados.

## Impacto técnico

- Quem já usa dict ou CrossModuleQuery (Pydantic) continua funcionando.
- Novos usos podem instanciar `QueryJson(...)` e passar para `execute_query_json` ou chamar `query.to_dict()` e passar o dict.

## Impacto externo

- Nenhuma quebra; apenas nova API opcional.

## Como validar

- Instanciar `QueryJson(document="Contact", relations=[QueryRelation(...)])`, chamar `to_dict()` e verificar keys em camelCase.
- Chamar `client.execute_query_json(query_json_instance)` e verificar que a requisição é enviada corretamente.

## Arquivos afetados

- `KonectySdkPython/lib/feature_types/query_json.py` (novo)
- `KonectySdkPython/lib/feature_types/__init__.py` (exports)
- `KonectySdkPython/lib/services/query.py` (aceitar to_dict)
- `docs/api.md`, `.cursor/skills/konecty-sdk-python/SKILL.md`, `reference.md`

## Existe migração?

Não. Uso opcional.
