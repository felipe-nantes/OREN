# OpenSwissHCC v15 — piloto crítico com 32 cortes

Data: 2026-07-16

## Conclusão

O piloto crítico v15 foi aprovado para iniciar a coorte cega de desenvolvimento.
O mesmo caso que excedeu 180 segundos no v14 foi executado duas vezes com a
representação v15 e terminou em 20,5235 s e 16,9841 s.

As probabilidades foram idênticas nas duas passagens. Nenhum label foi lido e o
holdout permaneceu fechado.

## Alteração em relação ao v14

Foi alterado somente o teto de amostragem axial:

```text
v14: até 50 cortes
v15: exatamente 32 cortes equidistantes nos 87 casos
```

Modelo, prompt, fase, método de escore, classes, contrato e salvaguardas foram
preservados.

## Bundle cego v15

- casos: 87;
- cortes mínimos/medianos/máximos: 32/32/32;
- casos com 32 cortes: 87;
- assinatura:
  `0a4fc6272985ca266d5ac0659e441a2da39af941a6b34119100ffc3255450993`;
- SHA-256 de `bundle.json`:
  `ff0933155f3a10b949b2cdaab553a0406783041c351667c930a669f9a692d897`;
- cobertura axial amostrada mínima: 41,04%;
- cobertura axial amostrada mediana: 62,85%;
- cobertura axial amostrada máxima: 92,88%;
- `ground_truth_read=false`;
- `holdout_opened=false`.

A redução de cobertura pode diminuir sensibilidade e deve ser tratada como
limitação. Ela foi definida antes de qualquer avaliação v15 com labels.

## Protocolo congelado

- assinatura:
  `d7f40621f6a224d51e4499bbddb4da1d170141ff830a082991c0a7f969388eb1`;
- SHA-256 do arquivo:
  `c5a14d4e2cb09afc7eaa881ca4e9be69d82d26afe0855b183b703e7357faf8a1`;
- contrato: `dtwin-medgemma-volume-score-v1`;
- método: `first_token_restricted_softmax_v1`;
- requisições por caso na coorte: 1;
- retries automáticos: 0;
- gate final: 180 s;
- gate conservador do piloto: 150 s.

## Caso crítico

```text
case_id: anon-openswiss-7e1337c532007417
cortes no v14: 44
cortes no v15: 32
```

| Réplica | Tempo externo | Resultado | Gate 150 s |
|---|---:|---|---|
| 1 | 20,5235 s | `NEGATIVA` | aprovado |
| 2 | 16,9841 s | `NEGATIVA` | aprovado |

Probabilidades restritas idênticas:

| Classe | Escore |
|---|---:|
| `POSITIVA` | 0,19402669 |
| `NEGATIVA` | 0,46544588 |
| `INCONCLUSIVA` | 0,34052745 |

Diferença absoluta entre réplicas: `0.0` para as três classes.

## Integridade

- réplica 1:
  `66dc3a17e4f427084210715de31bfdae3686f4c6377768bcf10c6c8d888bc2c4`;
- réplica 2:
  `8664478f08d68809040af2cf6997c387eb8471f3f6c3b77731f8d0fd165d68e1`;
- resumo:
  `25c12dcc435c0667b3185cb4f6f1a1fcb14fcb22efdd99583f5ce7ccd6594e5c`.

## Próxima etapa

Executar os 87 casos cegos v15. A coorte deve abortar na primeira falha de
contrato ou tempo. Somente 87/87 resultados válidos permitirão congelar a
avaliação e solicitar autorização específica para abrir novamente apenas os
labels de desenvolvimento.

