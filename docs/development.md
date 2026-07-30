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

- **Versão:** Alterar `version` no pyproject.toml antes de publicar. É a única fonte de verdade da versão — o `setup.py` na raiz está defasado e não participa do build (o backend é hatchling).
- **Publicação (caminho normal):** workflow **Publish**, disparado à mão na aba Actions (`Run workflow`). Nenhum merge publica sozinho. O workflow roda `uv sync --extra dev`, `pytest`, consulta o PyPI e **falha antes do build se a versão do pyproject.toml já existir**, depois builda em `dist-build/` e envia com `uv publish`. Autentica pelo secret `PYPI_API_TOKEN` do repositório.
- **Build local:** `uv build` na raiz (artefatos em dist/).
- **Publicação manual (fallback):** `uvx twine upload --config-file .pypirc --skip-existing dist/*`. Mesmo endpoint (`upload.pypi.org/legacy/`) e mesmo tipo de API token; as credenciais vêm do `.pypirc`, que é gitignored e só existe localmente — daí o CI usar secret. Diferença de comportamento: `--skip-existing` pula em silêncio versões já publicadas, enquanto o workflow falha; e é ele que evita que um `dist/` local acumulado reenvie artefatos antigos.

## Testes

O runner é o pytest, declarado no extra `dev` e configurado em `[tool.pytest.ini_options]` (testpaths `tests`, `asyncio_mode = "strict"`):

```sh
uv sync --extra dev
uv run pytest
```

São os mesmos dois comandos que o workflow **Publish** roda como portão antes de publicar.

## Formatação e qualidade

A lista de dependências inclui black para formatação. Aplicar as convenções do projeto antes de commitar.

## Documentação e skill do agente

Alterações que afetem a API pública do SDK (novos ou removidos exports em `__init__.py`, novos ou alterados métodos no KonectyClient ou em tipos públicos, novos endpoints utilizados, mudança de comportamento ou de env vars) devem ser refletidas na documentação em `docs/` e na skill do agente em `.cursor/skills/konecty-sdk-python/`. Atualize SKILL.md e reference.md na mesma mudança em que alterar o código, para manter a skill atualizada. Detalhes do que revisar estão na seção "Maintainers: keeping the skill updated" do próprio SKILL.md.
