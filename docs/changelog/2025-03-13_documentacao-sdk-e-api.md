# Changelog — 2025-03-13

## Resumo

Criação da documentação obrigatória do projeto na pasta docs/, com descrição da API Konecty utilizada pelo SDK, guia de desenvolvimento e changelog.

## Motivação

O repositório não possuía documentação estruturada em docs/. As regras do workspace exigem documentação técnica em markdown (sem trechos de código nos .md), changelog e ADRs quando aplicável. A documentação permite que desenvolvedores e usuários do SDK entendam o contrato da API e como contribuir.

## O que mudou

- Criada a estrutura docs/ com README (índice), api.md (endpoints, autenticação, parâmetros de find, formatos de criação/atualização/exclusão e upload) e development.md (ambiente, variáveis de ambiente, estrutura do pacote, build e publicação).
- Conteúdo de api.md baseado no mapeamento existente do SDK e na consulta ao código-fonte do Konecty (rotas REST, módulos de data e stream, Filter).
- Criado docs/changelog/ com README (índice) e esta entrada.
- Criado docs/adr/ com ADR 0001 referente à adoção da estrutura de documentação.

## Impacto técnico

- Nenhuma alteração em código do SDK ou CLI; apenas adição de arquivos de documentação.
- Novos contribuidores e consumidores do pacote passam a ter referência centralizada para API e desenvolvimento.

## Impacto externo

- Usuários do SDK podem consultar docs/ para entender quais endpoints são utilizados e como configurar ambiente e token.
- Projeto alinhado às regras de documentação do workspace.

## Como validar

- Ler docs/README.md e seguir os links para api, development e changelog.
- Conferir que api.md descreve corretamente os endpoints utilizados pelo client e file_manager (find, find_by_id, create, update, delete, get_document, upload).
- Verificar que development.md reflete a estrutura atual do pacote e os comandos de build (uv build, twine).

## Arquivos afetados

- docs/README.md (novo)
- docs/api.md (novo)
- docs/development.md (novo)
- docs/changelog/README.md (novo)
- docs/changelog/2025-03-13_documentacao-sdk-e-api.md (novo)
- docs/adr/0001-estrutura-documentacao.md (novo)

## Existe migração?

Não. Nenhuma mudança em comportamento ou contrato do SDK.
