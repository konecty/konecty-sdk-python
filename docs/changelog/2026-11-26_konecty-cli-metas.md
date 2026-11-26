# `konecty-cli metas`: metadado de base + delta

## Resumo

Novo grupo de comandos `konecty-cli metas` (`montar`, `gerar-delta`, `linter`, `diff`, `aplicar`,
`deriva`), fase 3 da feature `metadados-base-e-delta` do `konecty/Konecty` (T12–T19).

## Motivação

Cada cliente imobiliário mantinha uma cópia completa do metadado e aplicava direto no Mongo. Com o
`metas`, o repositório do cliente guarda só o delta sobre a `metadata/base`, o CI monta um artefato
determinístico e um Job aplica pela API (`POST /api/document` em lote, com `dryRun`), sem credencial
de banco, gravando `metadataVersion` (identidade do artefato) e `metadataAplicacao` (data, autor,
commit) no Namespace. Se o Namespace muda é o `plan.namespace` do `dryRun` que diz, porque o PAT não lê
o Namespace.

## O que mudou

- `KonectySdkPython/cli/metas/`: leitura de árvore com hooks, Merge Patch RFC 7386 com `{"$null": true}`,
  montagem, migração, linter, diff, aplicação e deriva.
- Nova dependência: `pyyaml` (leitura do `metadados.yaml`).
- Documentação em `docs/cli-metas.md` e na skill.

## Impacto técnico

Nenhuma mudança no client REST nem nos comandos `apply`/`backup`/`pull`. Só Python: o SDK TypeScript
não tem CLI de metadado.
