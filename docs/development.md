# Desenvolvimento do Konecty SDK Python

## Ambiente

- **Python:** 3.11 ou superior (definido em pyproject.toml e .python-version).
- **Gerenciador de pacotes:** O projeto utiliza uv para dependências e build (uv.lock na raiz). Alternativamente é possível usar pip com o pyproject.toml.

## Variáveis de ambiente

Para uso do cliente contra uma instância Konecty:

- **KONECTY_URL** — URL base da API (ex.: `http://localhost:3000`). Valor padrão: `http://localhost:3000`.
- **KONECTY_TOKEN** — Token de autenticação enviado no header Authorization em todas as requisições REST.

O módulo settings.py usa essas variáveis ao instanciar KonectyClient em fill_settings e fill_settings_sync.

## Estrutura do pacote

- **KonectySdkPython/** — Pacote principal.
  - **lib/** — Lógica do SDK: client (KonectyClient, find/create/update/delete, get_document, get_setting(s), count_documents, upload_file), filters (KonectyFilter, KonectyFindParams, operadores e ordenação), types (KonectyDateTime, KonectyUpdateId, modelos de dados Konecty), file_manager (upload de arquivo), settings (fill_settings a partir do Konecty ou env), model (base para documentos).
  - **cli/** — Aplicação de linha de comando (konecty-cli): grupo principal, comandos apply, backup, pull. Interagem com MongoDB para metadados; não substituem o uso do client para a API REST.

O ponto de entrada do script instalável é KonectySdkPython.cli:main, registrado como `konecty-cli` no pyproject.toml.

## Build e publicação

- **Build:** Na raiz do repositório, usar `uv build` (ou o equivalente com hatchling via pip). O build produz artefatos no diretório dist/.
- **Versão:** Alterar a versão no pyproject.toml antes de gerar um novo build.
- **Publicação:** Exemplo com twine: `uvx twine upload --config-file .pypirc --skip-existing dist/*` (credenciais e repositório configurados em .pypirc).

## Testes

O projeto não declara um runner de testes no pyproject.toml. Para rodar testes, usar o comando ou ferramenta de teste adotada pelo repositório (por exemplo pytest ou unittest), se configurado.

## Formatação e qualidade

A lista de dependências inclui black para formatação. Aplicar as convenções do projeto antes de commitar.

## Documentação e skill do agente

Alterações que afetem a API pública do SDK (novos ou removidos exports em `__init__.py`, novos ou alterados métodos no KonectyClient ou em tipos públicos, novos endpoints utilizados, mudança de comportamento ou de env vars) devem ser refletidas na documentação em `docs/` e na skill do agente em `.cursor/skills/konecty-sdk-python/`. Atualize SKILL.md e reference.md na mesma mudança em que alterar o código, para manter a skill atualizada. Detalhes do que revisar estão na seção "Maintainers: keeping the skill updated" do próprio SKILL.md.
