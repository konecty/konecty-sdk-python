# AGENTS.md

Guia para agentes de IA (Claude Code, Cursor, etc.) neste repositório.

> Este arquivo é `AGENTS.md`; `CLAUDE.md` é um symlink para ele. **Edite `AGENTS.md`.**

`konecty-sdk-python` — SDK **Python** do Konecty. Cliente HTTP assíncrono sobre as APIs REST do backend (`konecty/Konecty`), mais uma CLI (`konecty-cli`) para metadados.

## O SDK tem um par: mantenha os dois em sincronia

Existem **dois SDKs oficiais do Konecty**, e eles são pares — não um principal e um secundário:

| | repo | pacote |
| --- | --- | --- |
| Python | `konecty/konecty-sdk-python` (este) | `konecty-sdk-python` (PyPI) |
| TypeScript | `konecty/konecty-sdk` | `@konecty/sdk` (npm) |

- **Mudou algo aqui que também existe lá? Provavelmente muda lá também.** Vale para método novo, campo novo, código de erro novo, correção de comportamento e mudança de assinatura. Antes de fechar a task, **verifique o SDK TypeScript** e diga o que encontrou: ou você espelhou, ou não se aplica (e por quê), ou fica para uma task própria (e diga qual).
- **Nem tudo espelha, e tudo bem — mas justifique.** Exemplo real: `exchange_google_code` passou a lançar `KonectyGoogleSessionError` com `code` espelhando o TypeScript, porque o buraco era o mesmo; já os helpers puros que não gravam cookie **não** vieram para cá — eram exigência de um consumidor de browser, e aqui a sessão é adotada no objeto do client.
- **Mesma entrada, mesma saída.** Onde os dois expõem a mesma operação, o comportamento observável tem que bater. Duas armadilhas específicas do Python, ambas já encontradas na prática:
  - **Query string:** `urlencode` usa `quote_plus` por padrão e transforma espaço em `+`; `encodeURIComponent` produz `%20`. Use o helper `_encode_query` em `KonectySdkPython/lib/services/auth.py`, que já replica o conjunto seguro do JavaScript.
  - **Códigos de erro:** o conjunto reconhecido e o fallback (`failed`) precisam ser os mesmos dos dois lados, senão o mesmo corpo de resposta produz códigos diferentes por linguagem.
- **Trave a paridade por teste, não por comentário.** Ao espelhar, escreva aqui um teste com **a mesma entrada e a mesma saída esperada** do teste equivalente lá. Ver `tests/test_auth_google.py` e `src/__test__/api/googleLogin.test.ts` no TypeScript.

E na direção do backend: mudança na superfície pública do `konecty/Konecty` (rota, campo de resposta, código de erro) precisa chegar **aos dois SDKs**. Um atualizado e o outro não é a falha mais comum, e ela só aparece quando um cliente da outra linguagem quebra.

## Publicação

- **Disparo manual:** aba Actions → **Publish** → `Run workflow`, escolhendo o incremento (`patch`, `minor`, `major`). Nenhum merge publica sozinho.
- **Não edite a versão à mão.** O bump faz parte do publish: o workflow escreve `version` no `pyproject.toml` com `uv version --bump`, publica e **só então** commita `chore(release): <versão>` e taggeia. A ordem é deliberada — upload que falha não pode deixar na `main` um bump anunciando versão que não existe no PyPI.
- `pyproject.toml` é a única fonte de verdade da versão. O `setup.py` da raiz está defasado e não participa do build (o backend é hatchling).
- Requer o secret `PYPI_API_TOKEN`.

## Testes

```sh
uv sync --extra dev
uv run pytest
```

São os mesmos dois comandos que o workflow **Publish** roda como portão. Os testes usam um servidor HTTP stub (`stub_server`) e assertam o **contrato observável** — URL, corpo enviado, status, exceção lançada e estado do client depois — e não a implementação interna.

Ao corrigir um bug, escreva primeiro o teste que o reproduz. Nunca enfraqueça ou delete um teste para fazer a suíte passar.

## Convenções

- **Sem credenciais/segredos hardcoded.** Tokens e URLs de teste são fictícios; nada de literal apontando para deployment real. O `.pypirc` é gitignored e nunca deve ser commitado.
- **Nada de `authId` em URL, log ou mensagem de erro.** O token de sessão só trafega em corpo de resposta e em header `Authorization`.
- **Erros carregam código legível por máquina** quando o backend fornece um, e a exceção específica **subclasseia** a genérica (`KonectyGoogleSessionError` < `KonectyAPIError`), para não quebrar quem já capturava a genérica.
- **Documentação:** mudanças na API pública (novos exports, métodos, endpoints, env vars) se refletem em `docs/` e na skill em `.cursor/skills/konecty-sdk-python/`, na mesma mudança que altera o código.
- **Verifique, não chute.** Ao mexer em contrato do backend, confira `docs/pt-BR/api.md` no repo `konecty/Konecty` em vez de recordar de memória.
