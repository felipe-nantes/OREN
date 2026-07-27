# OpenSwissHCC v14 — protocolo de escore volumétrico contínuo

Data do congelamento conceitual: 2026-07-15

## 1. Motivação

O v13 demonstrou que a entrada 3D nativa é tecnicamente viável no MedGemma
1.5 4B e atende ao teto operacional de 180 segundos, mas sua decisão textual
discreta falhou no desenvolvimento:

- sensibilidade: 51,28%;
- especificidade: 31,25%;
- 19 respostas inconclusivas;
- 87/87 casos processados em até 180 segundos.

A comparação v11×v13 mostrou complementaridade de erros, mas nenhuma regra
categórica simples é defensável. O teto-oráculo foi 87,18% de sensibilidade e
83,33% de especificidade, porém ele usa o ground truth para escolher a resposta
por caso e não constitui uma métrica de modelo.

O v14 deve medir a evidência contínua do modelo para as três classes, sem
treinar ou modificar seus pesos. O objetivo é permitir calibração reproduzível
no conjunto de desenvolvimento e avaliar se a informação volumétrica ajuda de
forma estável quando combinada com os sinais v11.

Não existe garantia prévia de atingir 75%/75%. O holdout continuará fechado até
que todos os gates definidos neste documento sejam cumpridos.

## 2. Escopo e invariantes

O v14 preserva:

- modelo `google/medgemma-1.5-4b-it`;
- pilhas 3D aprovadas do desenvolvimento, com 35–50 cortes por caso;
- instrução pathology-target do v13;
- ordenação axial e hashes dos stacks;
- uma requisição sequencial por caso e zero retries automáticos;
- endpoint exclusivamente local;
- ausência de ground truth, máscara de lesão e PHI na inferência;
- `research_only=true`, `clinical_use_allowed=false` e revisão humana;
- limite máximo de 180 segundos por caso;
- holdout fechado.

O v14 não substitui nem altera `/generate-volume` ou o contrato
`dtwin-medgemma-volume-v1`. Ele adiciona um contrato isolado.

## 3. Contrato de pontuação

Endpoint novo:

```text
POST /score-volume
```

Contrato:

```text
dtwin-medgemma-volume-score-v1
```

O request reutiliza `model_id`, `model_version`, `instruction`, `images` e
`query`. A seção de pontuação aceita somente o prefixo protegido:

```json
{
  "response_prefix": "{\"resultado_hipotese\":\""
}
```

As classes não são fornecidas pelo navegador nem pelo benchmark. O servidor
mantém a lista fixa e ordenada:

```text
POSITIVA
NEGATIVA
INCONCLUSIVA
```

Campos extras são proibidos. Os limites atuais de quantidade, formato, bytes e
pixels das imagens permanecem idênticos aos de `/generate-volume`.

## 4. Definição matemática do escore

O runtime monta a mesma conversa multimodal do v13 e anexa o mesmo prefixo à
entrada tokenizada. Em uma única passagem direta do modelo, obtém os logits da
próxima posição.

Para cada classe `c`, seja `t(c)` o primeiro token gerado pelo tokenizer sem
tokens especiais. O servidor calcula:

```text
p(c) = exp(logit[t(c)]) / soma_k exp(logit[t(k)])
```

para as três classes permitidas.

Nome obrigatório do método:

```text
first_token_restricted_softmax_v1
```

Esse valor é uma probabilidade relativa restrita aos primeiros tokens das três
continuações. Ele não deve ser apresentado como probabilidade clínica nem como
probabilidade da sequência textual completa.

Gates antes de pontuar:

- cada classe precisa produzir pelo menos um token;
- os três primeiros token IDs devem ser distintos;
- todos os logits e valores derivados devem ser finitos;
- as probabilidades devem estar no intervalo `[0, 1]`;
- a soma deve ser 1 dentro de tolerância numérica de `1e-6`;
- empate no maior valor deve ser resolvido pela ordem fixa acima e registrado;
- qualquer violação invalida o caso, sem fallback para geração textual.

Resposta mínima:

```json
{
  "contract": "dtwin-medgemma-volume-score-v1",
  "model_id": "google/medgemma-1.5-4b-it",
  "model_version": "...",
  "slice_count": 50,
  "choice": "POSITIVA",
  "choice_probabilities": {
    "POSITIVA": 0.0,
    "NEGATIVA": 0.0,
    "INCONCLUSIVA": 0.0
  },
  "scoring_method": "first_token_restricted_softmax_v1",
  "choice_token_metadata": {},
  "timings_seconds": {},
  "research_only": true,
  "clinical_use_allowed": false,
  "requires_human_review": true
}
```

Os metadados de token servem apenas à auditoria técnica e não podem conter o
prompt completo, imagens, PHI ou dados protegidos.

## 5. Artefato cego por caso

Cada resultado v14 deve persistir atomicamente:

- `case_id`;
- assinatura do protocolo;
- SHA-256 do manifesto da pilha;
- contagem de cortes;
- três probabilidades restritas;
- classe de maior escore;
- método de pontuação;
- metadados dos tokens das classes;
- tempo do gateway e tempo externo;
- resultado do gate de 180 segundos;
- flags de segurança;
- `ground_truth_read=false`, `metrics_calculated=false` e
  `holdout_opened=false` durante a inferência.

Resultados existentes nunca serão sobrescritos. Retomada só é permitida quando
assinatura do protocolo, hashes e IDs coincidirem exatamente.

## 6. Ordem de implementação

### Etapa A — servidor e contrato

1. Criar modelos Pydantic isolados para o request v14.
2. Extrair a validação comum das imagens sem alterar o comportamento v13.
3. Implementar `score_volume` com uma passagem direta e softmax restrito.
4. Criar `/score-volume`.
5. Anunciar suporte e contrato no health check.
6. Preservar integralmente `/generate` e `/generate-volume`.

### Etapa B — testes do servidor

Testar:

- contrato válido;
- campos extras rejeitados;
- modelo e versão divergentes rejeitados;
- runtime incompatível e modelo não carregado;
- 4 ou 86 imagens rejeitadas;
- PNG inválido, dimensões, bytes e pixels excessivos;
- tokenizações vazias ou primeiros tokens duplicados;
- logits não finitos;
- normalização e escolha determinística;
- flags de segurança;
- endpoint v13 sem regressão.

### Etapa C — protocolo e cliente cego v14

1. Criar congelador próprio do protocolo v14.
2. Assinar conteúdo canônico antes da primeira chamada.
3. Validar novamente todos os hashes das pilhas.
4. Persistir um resultado por caso e um resumo retomável.
5. Impedir qualquer leitura de labels pelos módulos de inferência.

### Etapa D — piloto técnico cego

Executar inicialmente um caso já pertencente ao bundle de desenvolvimento,
sem abrir labels no processo de inferência. O piloto passa somente se:

- o contrato e o health check coincidirem;
- as três probabilidades forem válidas e reproduzíveis;
- duas execuções controladas gerarem os mesmos escores dentro de `1e-6`;
- cada execução terminar em até 180 segundos;
- nenhum artefato protegido entrar no request ou no resultado.

Se o piloto falhar, o v14 é corrigido ou abandonado antes da coorte completa.

### Etapa E — inferência cega nos 87 casos

Após o piloto aprovado:

- congelar definitivamente a assinatura da coorte;
- processar 87/87 casos sem labels;
- validar completude, unicidade, hashes e tempos;
- gerar o resumo cego;
- somente então permitir a junção tardia com os labels de desenvolvimento.

## 7. Avaliação e calibração no desenvolvimento

O escore volumétrico primário será:

```text
v14_log_odds = log((p(POSITIVA) + 1e-8) / (p(NEGATIVA) + 1e-8))
```

`p(INCONCLUSIVA)` permanece uma variável explícita de incerteza. Não será
redistribuída silenciosamente entre positivo e negativo.

As análises permitidas são:

1. v14 isolado com limiar;
2. v11 isolado, reproduzido como controle;
3. combinação de variáveis v11 congeladas com `v14_log_odds` e
   `p(INCONCLUSIVA)`.

Toda escolha de limiar, variável ou regra deve ocorrer dentro de validação
cruzada aninhada. O fold externo nunca participa da seleção realizada no fold
interno. Devem ser reportados:

- predições out-of-fold por caso;
- matriz de confusão penalizada;
- sensibilidade e especificidade com IC95%;
- distribuição dos resultados em divisões repetidas estratificadas;
- estabilidade dos coeficientes/limiares;
- cobertura e taxa de inconclusivos;
- tempo por caso.

`INCONCLUSIVA` continua contando como erro na métrica principal. Não é permitido
escolher uma regra após consultar o desempenho do mesmo fold usado para
reportá-la.

## 8. Gates para avançar ao holdout

O holdout só poderá ser considerado para uma única avaliação final se uma
configuração previamente congelada cumprir simultaneamente no desenvolvimento:

- sensibilidade out-of-fold ≥ 75%;
- especificidade out-of-fold ≥ 75%;
- limite de 180 segundos cumprido em 100% dos casos;
- pelo menos 80% das repetições estratificadas cumprindo ambos os gates;
- nenhum vazamento de ground truth ou máscara de lesão;
- 87 resultados válidos, únicos e auditáveis;
- regra final, limiares e hashes congelados antes do holdout;
- revisão humana obrigatória preservada.

Se os gates não forem cumpridos, o holdout permanece fechado e o resultado deve
ser documentado como novo teto experimental sem treinamento próprio.

## 9. Critérios de parada e interpretação

O v14 será interrompido se:

- o tokenizer não produzir primeiros tokens distintos;
- o piloto não for determinístico;
- qualquer caso exceder 180 segundos sem causa técnica corrigível;
- a inferência exigir redução de salvaguardas;
- a validação aninhada não atingir ou não estabilizar 75%/75%.

Mesmo em caso de sucesso, o resultado comprovará desempenho experimental apenas
na base pública e não desempenho clínico em exames locais.

