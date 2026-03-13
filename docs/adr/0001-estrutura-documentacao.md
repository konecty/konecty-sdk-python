# ADR 0001 — Estrutura de documentação em docs/

## Status

Aceito.

## Data

2025-03-13.

## Contexto

O repositório do Konecty SDK Python não possuía documentação centralizada. As regras do workspace exigem documentação em docs/ (apenas arquivos .md), changelog e ADRs para decisões que afetem arquitetura ou padrões do projeto. Era necessário definir onde e como documentar o SDK e a API utilizada.

## Decisão

- Adotar a pasta **docs/** na raiz do repositório para toda a documentação técnica em markdown.
- Incluir em docs/: README (índice), api.md (contrato da API Konecty usada pelo SDK), development.md (ambiente, estrutura, build), changelog/ (entradas por data) e adr/ (Architecture Decision Records).
- Documentação técnica e objetiva, sem blocos de código nos .md; referências a nomes de arquivos e símbolos são permitidas.
- Toda alteração relevante deve gerar entrada em docs/changelog/ e atualização do índice em docs/changelog/README.md. ADRs devem ser criados quando houver decisões que afetem arquitetura, dependências ou padrões estruturais.

## Alternativas consideradas

- Manter documentação apenas no README da raiz: insuficiente para API, desenvolvimento e histórico de mudanças.
- Documentação em wiki ou site externo: fragmenta a referência e não fica versionada com o código.
- Incluir trechos de código nos .md: as regras do workspace proíbem código em docs/; a referência é por nomes de módulos e símbolos.

## Consequências

- Desenvolvedores e usuários têm um único lugar (docs/) para entender a API, o desenvolvimento e o changelog.
- O projeto fica alinhado às regras de documentação do workspace.
- Novos ADRs devem seguir a estrutura obrigatória (Título, Status, Data, Contexto, Decisão, Alternativas consideradas, Consequências, Plano de implementação quando aplicável, Referências) e o padrão de nome NNNN-titulo-da-decisao.md.

## Plano de implementação

- Criar docs/README.md, docs/api.md, docs/development.md.
- Criar docs/changelog/README.md e entrada para a data da adoção.
- Criar docs/adr/ e este ADR (0001-estrutura-documentacao.md).
- Em entregas futuras, manter changelog e ADRs atualizados conforme as regras do projeto.

## Referências

- Regras do workspace (Documentação obrigatória): estrutura docs/, changelog e ADR.
- Código-fonte do Konecty (rotas REST, data API, Filter) para precisão de api.md.
