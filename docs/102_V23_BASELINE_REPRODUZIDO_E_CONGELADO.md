# V23 — baseline reproduzido e congelado

## Escopo

Esta etapa consolidou exclusivamente o baseline v23 existente. Nenhuma feature,
regra, peso, normalização ou limiar foi alterado.

O baseline permanece:

```text
80% do sinal v11
20% da linearidade ponderada dos candidatos
```

Ele é um resultado retrospectivo de desenvolvimento. Não qualifica o sistema
final e não autoriza reutilizar o holdout v21.

## Reprodução independente

Duas avaliações foram executadas em destinos isolados usando o bundle v20, o
protocolo v20, as features geométricas v23 e os 87 labels públicos de
desenvolvimento já autorizados.

As duas reproduções foram byte a byte idênticas ao resultado oficial:

```text
evaluation.json:
  70c43566a20ddd9d1f9ed50bbb6c1db5b6e5b89de0e0fb77fce04b39b35a237f

case_scores.csv:
  6f197c71d3ca5a544f5d22e52fdb0289b16a80c15336ae86dea7358aa7372d0b
```

Resultado reproduzido:

```text
TP=32  TN=38  FP=10  FN=7
sensibilidade=82,05%
especificidade=79,17%
balanced accuracy=80,61%
```

A validação repetida permaneceu em 49/50 execuções aprovadas em 75/75. O gate
de robustez integral continua reprovado, porque uma repetição atingiu somente
71,79% de sensibilidade.

## Calibrador

O calibrador foi regenerado em destino isolado e ficou byte a byte idêntico ao
oficial:

```text
arquivo SHA-256:
  69a8c110dd42e7cdf7e2906e337981fd678b4040ad7074fc4012f5af5c2a578d

assinatura interna:
  d0a955178783cf7f2914053c87d3d99d186ab4a56960620068bd118e5ccac475

limiar:
  0.5121839080459771
```

## Lock verificável

O inventário congelado está em:

```text
configs/benchmark/openswisshcc_v23_baseline_lock_v1.json
```

Ele fixa hashes e tamanhos do código principal, entradas, avaliação, scores,
calibrador e timing. A verificação é executada com:

```powershell
.\.venv-win\Scripts\python.exe tools\verify_openswisshcc_v23_baseline.py
```

O verificador falha se qualquer artefato estiver ausente, truncado ou alterado;
se pesos, métricas, assinatura, flags de segurança ou escopo temporal
divergirem; ou se o lock tentar apontar para fora do workspace.

## Testes

Foram executados os testes do extrator geométrico, timing, fusão v23 e contratos
LLD-MMRI relacionados:

```text
33 passed
```

O verificador do lock possui testes adicionais de sucesso, adulteração e caminho
inseguro.

## Estado temporal

O limite conservador do pipeline preparado permanece em 107,7983 segundos e
passa o teto de 180 segundos. Isso ainda não comprova o tempo end-to-end desde
o DICOM bruto.

## Próximo gate

O baseline v23 está reproduzido e protegido contra alteração silenciosa. A
próxima etapa poderá auditar os 7 falsos negativos e 10 falsos positivos sem
modificar este baseline. Novas hipóteses deverão ser implementadas em módulos e
artefatos separados.
