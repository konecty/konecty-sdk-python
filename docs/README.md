# Documentação do Konecty SDK Python

Este diretório contém a documentação técnica do SDK Python para integração com a plataforma [Konecty](https://github.com/konecty/Konecty).

## Propósito do SDK

O Konecty SDK Python expõe um cliente para interagir com a API REST do Konecty (CRM / plataforma de negócios) e uma CLI para operações com o banco de dados de metadados (apply, backup, pull).

## Índice

- [api](api.md) — Contrato da API Konecty utilizada pelo SDK: endpoints, autenticação, parâmetros de find, formatos de requisição e resposta.
- [development](development.md) — Ambiente de desenvolvimento, estrutura do pacote, build e variáveis de ambiente.
- [changelog](changelog/README.md) — Histórico de alterações do projeto.
- [adr](adr/) — Architecture Decision Records para decisões relevantes de arquitetura (ex.: 0001-estrutura-documentacao).

## Skill para agentes (Cursor)

O repositório inclui uma skill de agente em `.cursor/skills/konecty-sdk-python/` (SKILL.md e reference.md). Projetos que utilizam o SDK podem copiar essa pasta para o próprio `.cursor/skills/` ou referenciá-la para que o agente entenda funcionalidades, módulos exportados, uso e boas práticas do SDK.

**Manutenção:** Atualizações no código do SDK que alterem a API pública (exports, métodos do client, tipos, CLI, endpoints ou comportamento) devem ser refletidas na skill. Ao modificar o que o pacote expõe ou como ele funciona, atualize o conteúdo de SKILL.md e reference.md na mesma alteração, para que a skill continue alinhada ao código. O próprio SKILL.md contém a seção "Maintainers: keeping the skill updated" com o checklist; em development.md consta o lembrete no fluxo de desenvolvimento.
