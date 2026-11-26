# `konecty-cli metas`: metadado de base + delta por cliente

Implementa o componente M da feature `metadados-base-e-delta` do `konecty/Konecty`
(`.specs/features/metadados-base-e-delta/`). O repositório do cliente guarda só o que difere da
`metadata/base`; a CLI monta o metadado final, compara, confere e aplica pela API, sem Mongo.

Só existe no SDK Python. O SDK TypeScript (`@konecty/sdk`) não tem CLI de metadado; o que os dois
compartilham é `apply_meta_bulk` / `applyMetaBulk`, que este comando usa.

## Repositório do cliente

```
metadados.yaml           # cliente, base, konecty, versao?, removidos[], naoMigrados[]
delta/<Módulo>/...       # mesma árvore da base: .json = Merge Patch (RFC 7386); hook/*.js substitui
delta/Namespace.json     # Merge Patch sobre o Namespace.json da base
modulos/<Módulo>/...     # módulo só do cliente, árvore completa (ou cópia integral de um naoMigrados)
env/<ambiente>.env       # CHAVE=valor para os placeholders __CHAVE__, sem segredo
```

```yaml
cliente: auxiliadora
base: base-metas/v2.9.0
konecty: ">=3.19.0"
removidos:              # por _id de meta, não por módulo
  - Product:access:Corretor
naoMigrados: []         # módulos da base substituídos inteiros pela cópia em modulos/
```

Regras do delta:

- `null` apaga a chave; `{"$null": true}` grava `null` literal; lista é substituída inteira.
- `delta/<M>/hook/<nome>.js` troca o hook; `hook/<nome>.json` é Merge Patch sobre o hook da base.
  Para tirar um hook da base, ponha `"<nome>": null` no `delta/<M>/document.json`.
- Um `.json` do delta num caminho que a base não tem é um meta novo inteiro (precisa de `_id`).
- `delta/Namespace.json` com `null` numa chave tira a chave do patch do Namespace: ela fica como
  está no tenant (é o jeito de não gerenciar chaves com segredo, como `emailServers`).

## Comandos

| Comando | O que faz |
|---|---|
| `metas montar <repo> --ambiente dev\|prod --saida dist/ [--versao v1.2.0] [--base-dir D \| --base-repo URL] [--tar]` | Baixa `metadata/base` da tag de `metadados.yaml` (ou usa `--base-dir`), aplica `naoMigrados`, `modulos/`, o delta e os `removidos`, resolve os `__X__` por `env/<ambiente>.env` e grava o artefato. Falha nomeando o arquivo, a tag ou o token; falha acima de 16 MiB com o tamanho |
| `metas gerar-delta <base-dir> <cópia> --saida <repo> --cliente X --base <tag>` | Migração inicial: escreve `delta/`, `modulos/` e `metadados.yaml` a partir de uma cópia completa. Garante `montar(gerar-delta(base, cópia)) == cópia`. Não migra o `Namespace.json` (segredos) |
| `metas linter <repo> [--base-dir D]` | Erro para patch que repete a base, `null` em chave que a base não tem, campo novo sem `type` e módulo de `modulos/` com nome da base fora de `naoMigrados`; aviso para lista igual à da base. Sai com 1 se houver erro |
| `metas diff <dist-a> <dist-b> [--markdown]` | Diff por documento e chave (`fields.<campo>`, hooks marcados). `--markdown` para comentário de PR |
| `metas aplicar <dist> [--url URL]` | Confere sha256 e `ambiente` contra `TENANT_ENV` (código 2, nada enviado); `dryRun` com `namespacePatch` (`namespace.json` + `metadataVersion`); nenhum item a criar ou alterar e `plan.namespace.keys` vazio: `aplicados=0`; senão aplica só o que mudou com `hookMode: 'replace'` e o mesmo `namespacePatch` mais `metadataAplicacao`. 5xx/rede: 3 novas tentativas (5, 15, 45 s). 400: erros mapeados para `_id` e arquivo (código 1) |
| `metas deriva <dist> [--url URL] [--tenant T]` | Só `dryRun`. Imprime `konecty_metadata_drift_documents{tenant="T"} N` (linha para o Loki virar métrica) e a lista por documento e chave |

Variáveis de ambiente de `aplicar` e `deriva`: `KONECTY_URL` (ou `--url`), `KONECTY_TOKEN` (PAT de
service account com `metaApply`; vai só no header `Authorization`, nunca em log), `TENANT_ENV`
(`dev`/`prod`) e, opcional, `GIT_COMMIT` (vira `metadataAplicacao.origem`).

## Artefato

```
itens.json       # MetaObject[] completos, hooks embutidos, placeholders resolvidos, por _id
namespace.json   # patch do Namespace (sem _id, type, ns, que o core recusa no namespacePatch)
manifesto.json   # cliente, versaoCliente, base, konectyMin, ambiente, deltaBytes, deltaPct,
                 # naoMigrados, removidos, documentos {_id: sha256}, origens {_id: [arquivo]},
                 # sha256Total
```

- `sha256Total` = sha256 de `itens.json`, seguido de `namespace.json`, de `\n` e do `ambiente`. Com o
  ambiente no hash, editar só o `ambiente` do manifesto não leva um artefato de dev a prod. O de cada documento é o do JSON
  canônico (chaves ordenadas, sem espaço, UTF-8).
- `deltaBytes` soma os bytes dos arquivos do delta que existem na base; `deltaPct` é a razão sobre
  os bytes desses mesmos arquivos na base (emenda E1).
- Duas montagens do mesmo commit dão os mesmos bytes, inclusive o `.tar.gz` de `--tar`.

Gravado no Namespace:

- `metadataVersion`: `{cliente, versaoCliente, base, sha256, ambiente}`, a identidade do artefato. É
  estável: reaplicar o mesmo artefato dá o mesmo valor.
- `metadataAplicacao`: `{aplicadoEm, aplicadoPor, origem?}`, quando, por quem e de qual commit.

O PAT da service account não lê o Namespace (`/api/admin/meta/*` recusa PAT). Por isso o `aplicar`
manda o `namespacePatch` de identidade já no `dryRun`, e o core devolve em `plan.namespace.keys` as
chaves que mudariam (Konecty com `plan.namespace`; AD-MBD-003). Data e autor ficam fora do
`metadataVersion` para que essa comparação dê vazio quando nada mudou. Um tenant com os itens iguais
ao artefato e sem `metadataVersion` recebe a versão; um que já tem tudo igual não recebe escrita.

Requer um Konecty cujo `dryRun` devolva `plan.namespace`. Num core sem isso, o plano não traz a
chave e o `aplicar` só escreve quando há item a criar ou alterar.
