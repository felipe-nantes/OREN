# Ingestão monofásica experimental no OREN

## Objetivo

Permitir que uma RM hepática com somente uma série utilizável conclua o fluxo do
exame individual sem fabricar fases arterial, portal/venosa ou tardia.

## Decisão de roteamento

- Três fases identificadas com segurança: mantém o classificador visual
  trifásico validado.
- Fases dinâmicas insuficientes: usa `monophase_rag` com MedGemma 1.5 4B.
- Mais de um estudo ou conjunto de séries elegível: interrompe por ambiguidade.
- Uma organização de fases parcialmente curada continua sendo tratada como erro
  de entrada, não como autorização para adivinhar.

O erro do resolvedor possui código estruturado. Somente
`insufficient_dynamic_phases` autoriza o fallback.

## Representação monofásica

- Seleciona deterministicamente a melhor série real de RM.
- Segmenta o fígado em full resolution.
- Gera um painel com nove cortes sistematicamente distribuídos.
- Usa RAG textual auditado e prompt pathology-target específico.
- Não duplica a série em canais RGB e não sintetiza diferenças temporais.
- Gera `medgemma_report.json` e o visualizador 3D pelo contrato já existente.

Configuração autorizada:

```text
configs/medgemma_local_4b_monophase_rag.yaml
```

## Salvaguardas

O relatório e a interface registram:

- `dynamic_enhancement_information_present=false`;
- `synthetic_phases_created=false`;
- `validated_triphase_metrics_applicable=false`;
- ausência de avaliação de realce arterial, washout e persistência entre fases;
- amostragem limitada a nove cortes;
- revisão humana obrigatória e uso exclusivo em pesquisa.

As métricas de 75% do protocolo trifásico não são transferidas para este modo.
Ele exige benchmark monofásico próprio antes de qualquer alegação de acurácia.

## Validação prática de 2026-08-03

Caso real enviado pelo frontend:

```text
D:\lote_positivo_1_real\13.000000-t1vibeqfstrap2bhFIL-72776
```

Resultado técnico:

- cenário: `monophase_rag`;
- `medgemma_report.json`: gerado e validado;
- RAG: ativo;
- painéis enviados ao 4B: 1;
- tempo até o relatório: 141,68 s;
- tempo total com visualizador 3D: 170,85 s;
- orçamento de 180 s: atendido nas duas medições;
- visualizador: disponível para revisão humana.

O resultado clínico exploratório deste caso não constitui uma métrica. A
validação confirmou apenas integridade, segurança e tempo do pipeline.

## Testes executados

- 63 testes de webapp e resolução DICOM;
- 90 testes de painel, cliente, screening e timeout MedGemma;
- compilação de `dtwin` e `webapp`;
- execução real pelo seletor de pasta do frontend.
