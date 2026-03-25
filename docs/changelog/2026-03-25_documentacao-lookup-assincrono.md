# Documentação do lookup assíncrono

## Resumo

Atualiza a documentação para refletir a inclusão do método assíncrono de lookup no cliente do SDK.

## Motivação

O último commit adicionou suporte de lookup assíncrono no `KonectyClient`; a documentação precisava ficar alinhada ao comportamento atual da API exposta.

## O que mudou

- Inclusão do endpoint de lookup na tabela de endpoints utilizados pelo SDK.
- Criação de seção específica descrevendo parâmetros e contrato de resposta do lookup.
- Ajuste da seção de endpoints não utilizados para remover `lookup` da lista.

## Impacto técnico

A documentação técnica passa a representar corretamente o uso de `/rest/data/{module}/lookup/{lookup_field}` pelo SDK, reduzindo divergência entre implementação e referência.

## Impacto externo

Consumidores do SDK e mantenedores passam a ter orientação explícita para uso do método `lookup` assíncrono.

## Como validar

- Confirmar em `docs/api.md` a presença do endpoint de lookup na tabela principal.
- Confirmar em `docs/api.md` a seção de parâmetros do lookup com `search` opcional.
- Verificar que `lookup` não aparece mais na lista de endpoints não utilizados pelo SDK.

## Arquivos afetados

- `docs/api.md`
- `docs/changelog/2026-03-25_documentacao-lookup-assincrono.md`
- `docs/changelog/README.md`

## Existe migração?

Não.
