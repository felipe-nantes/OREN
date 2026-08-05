# OREN — segundo leitor monofásico implementável

**Data:** 4 de agosto de 2026  
**Estado:** implementado em modo de pesquisa; promoção automática bloqueada

## Problema resolvido

O classificador binário MedSigLIP para T1 tardio apresentou resultado interno útil no
LLD-MMRI, mas não manteve sensibilidade suficiente na validação externa OpenSwissHCC.
Aplicá-lo como decisor principal a qualquer DICOM monofásico atribuiria ao exame uma
métrica que não foi demonstrada no domínio de origem desconhecida.

## Solução implementada

O fluxo individual agora usa a seguinte hierarquia para entradas monofásicas:

1. o backend identifica a sequência real sem criar fases sintéticas;
2. o MedGemma 4B + RAG gera o relatório principal;
3. se a série foi identificada explicitamente como `T1_DELAYED`, o bundle MedSigLIP
   tardio é executado como segundo leitor;
4. concordância ou discordância é mostrada ao revisor;
5. o resultado MedSigLIP nunca altera automaticamente o relatório MedGemma;
6. para T2, DWI, ADC, arterial, portal ou fase desconhecida, o head tardio é recusado.

O segundo leitor é habilitado por padrão e pode ser desligado com:

```text
WEBAPP_MONOPHASE_DELAYED_MEDSIGLIP_ADVISORY=0
```

A promoção experimental antiga continua bloqueada por padrão:

```text
WEBAPP_MONOPHASE_DELAYED_MEDSIGLIP_AUTO_PROMOTED=0
```

## Artefato de auditoria

Cada execução monofásica persiste, quando aplicável:

```text
case/outputs/second_reader/medsiglip_advisory.json
```

O artefato registra:

- papel exclusivamente consultivo;
- decisão do leitor principal;
- decisão, score e limiar do segundo leitor;
- hash do manifesto dos painéis;
- concordância entre leitores;
- prioridade de revisão;
- latência;
- falha do gate externo;
- `affects_primary_decision=false`;
- pesquisa e revisão humana obrigatórias.

Uma falha do segundo leitor não apaga nem invalida um relatório MedGemma já validado.

## O que ainda não está qualificado

- Os percentuais internos do LLD-MMRI não se aplicam automaticamente a um DICOM
  aleatório.
- O MedSigLIP tardio não é o decisor final.
- O classificador de subtipo ainda não atingiu estabilidade suficiente para promoção.
- A promoção futura exige uma regra congelada que alcance pelo menos 75% de
  sensibilidade e 75% de especificidade em validação externa compatível.

## Verificação

Foram acrescentados testes para:

- execução somente em T1 tardio elegível;
- recusa de sequências incompatíveis antes da inferência;
- persistência atômica do segundo leitor;
- discordância elevando a prioridade de revisão;
- impossibilidade de o segundo leitor modificar o relatório primário;
- exposição segura do resultado no frontend.

Resultado da suíte completa nesta implementação:

```text
1410 passed, 0 failed
```

Smoke real na RTX 4060 com o MedGemma 4B já carregado:

```text
painéis: 3
latência adicional MedSigLIP: 7,7636 s
artefato persistido: sim
discordância marcada para revisão elevada: sim
decisão primária alterada: não
```
