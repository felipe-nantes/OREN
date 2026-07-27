# V23 retrospectiva multicohort — Fase 1

## Objetivo

Esta fase transforma o plano retrospectivo multicohort em um contrato
executável antes de montar inventários, rodar inferências ou recalcular
métricas.

Ela não altera o v23 congelado e não autoriza uma alegação de validação externa
cega. A única formulação permitida é:

> Desempenho retrospectivo multicohort nas bases disponíveis ao projeto.

## Regras congeladas

- endpoint primário: OpenSwissHCC por paciente e exclusivamente out-of-fold;
- pesos do v23: 80% v11 e 20% `candidate_weighted_linearity`;
- sensibilidade e especificidade mínimas: 75%;
- tempo máximo end-to-end desde DICOM bruto: 180 segundos;
- inconclusivos, timeouts, falhas técnicas e v23 não computável contam como
  erro;
- resultados secundários devem ser apresentados separadamente por base;
- LLD-MMRI positivo e CHAOS negativo não podem ser combinados para criar uma
  métrica primária artificial;
- CHAOS não qualifica o v23 exato por não possuir todas as fases dinâmicas;
- casos locais permanecem exploratórios até curadoria humana;
- nenhuma fase ausente pode ser fabricada;
- nenhum caso pode ser removido depois do congelamento do inventário.

## Dois estimandos distintos

1. **Primário retrospectivo:** arquitetura e pesos v23 fixos, com ECDF e limiar
   ajustados apenas dentro do treinamento de cada fold. Cada caso recebe uma
   predição out-of-fold.
2. **Calibrador congelado:** aplicação do limiar `0.5121839080459771` somente
   em entradas que reproduzam exatamente os quatro sinais v23. Esse resultado
   é secundário e não substitui o estimador out-of-fold.

Essa separação impede chamar de out-of-fold uma aplicação aparente do
calibrador que já viu parte do desenvolvimento.

## Papéis das bases

| Base | Papel | Pode qualificar 75/75 sozinha? |
|---|---|---|
| OpenSwissHCC | primária mista retrospectiva | sim, somente por OOF |
| LLD-MMRI | estresse secundário de sensibilidade | não |
| LiverHccSeg | sensibilidade secundária pequena | não |
| CHAOS | robustez visual de especificidade | não |
| casos locais | exploratório após curadoria | não |

## Comandos

Congelar o contrato:

```powershell
.\.venv-win\Scripts\python.exe tools\prepare_v23_retrospective_multicohort.py freeze
```

Verificar contrato e baseline:

```powershell
.\.venv-win\Scripts\python.exe tools\prepare_v23_retrospective_multicohort.py verify
```

Gerar o readiness sem abrir labels, máscaras ou pixels:

```powershell
.\.venv-win\Scripts\python.exe tools\prepare_v23_retrospective_multicohort.py readiness
```

## Próximo gate

A Fase 2 deverá:

1. vincular e hashear o inventário dos 132 casos OpenSwissHCC;
2. confirmar identidade única por paciente;
3. congelar os folds externos e o procedimento interno;
4. mapear quais sinais v23 já existem e quais precisam ser recomputados;
5. auditar compatibilidade v23 da LLD-MMRI e LiverHccSeg sem calcular métricas.

Até esse gate passar, `inference_authorized=false` e
`metrics_authorized=false` permanecem obrigatórios.
