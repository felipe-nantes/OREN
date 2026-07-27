# OpenSwissHCC v15 — protocolo de avaliação congelado

Data do congelamento: 16 de julho de 2026.

## Objetivo

Congelar uma única hipótese estatística antes da abertura dos labels protegidos de desenvolvimento. O protocolo combina dois leitores cegos já persistidos:

1. fusão v11 previamente congelada;
2. score volumétrico nativo v15 do MedGemma 1.5 4B, limitado a 32 cortes.

O holdout permanece fechado e nenhuma métrica clínica foi calculada nesta etapa.

## Candidato primário pré-especificado

O candidato primário é:

```text
0,50 × ECDF do leitor v11
+ 0,50 × ECDF do log-odds volumétrico v15
```

O leitor v11 preserva internamente seus pesos congelados:

- `medgemma_v4_uncertainty_margin`: 0,40;
- `medsiglip_v5_inverse_sagittal`: 0,40;
- `localizer_v10_log_volume`: 0,20.

O sinal v15 é:

```text
log((P(POSITIVA) + 1e-8) / (P(NEGATIVA) + 1e-8))
```

Não há ajuste de pesos após a abertura dos labels. A escolha de 50/50 representa dois leitores de nível superior com peso igual, preservando a composição interna já congelada do v11.

## Prevenção de vazamento

Em cada fold:

1. as ECDFs são construídas somente com os casos de treino;
2. os casos de teste são transformados usando exclusivamente a referência do treino;
3. o limiar é selecionado somente no treino;
4. o limiar maximiza primeiro o menor valor entre sensibilidade e especificidade e, depois, a acurácia balanceada;
5. nenhuma decisão do fold de teste influencia transformação, peso ou limiar.

## Avaliação pré-especificada

### Estimador primário

- leave-one-out cross-validation totalmente aninhada;
- sensibilidade e especificidade calculadas sobre todas as predições fora da amostra;
- intervalos de confiança de Wilson de 95%.

### Robustez obrigatória

- repeated stratified 5-fold;
- 50 repetições;
- seed base `20260716`;
- transformação e limiar novamente ajustados dentro de cada fold de treino.

### Gate de desenvolvimento

O candidato somente justifica a próxima etapa se cumprir simultaneamente:

- sensibilidade LOOCV ≥ 75%;
- especificidade LOOCV ≥ 75%;
- 50 de 50 repetições estratificadas com sensibilidade ≥ 75% e especificidade ≥ 75%;
- tempo conservador combinado ≤ 180 segundos.

Se o gate falhar, o holdout deve permanecer fechado.

## Diagnósticos secundários

Serão reportados, mas não poderão substituir o candidato primário:

- v11 isolado em LOOCV aninhada;
- v15 isolado em LOOCV aninhada;
- classificação categórica bruta v15.

Na classificação categórica bruta, `INCONCLUSIVA` conta como erro:

- em positivo, conta como falso negativo;
- em negativo, conta como falso positivo.

Essa regra impede que abstenções melhorem artificialmente sensibilidade ou especificidade.

## Tempo operacional

| Componente | Tempo conservador |
|---|---:|
| Pipeline v11 | 85,3486 s |
| MedGemma volumétrico v15 | 17,0126 s |
| Total conservador | 102,3612 s |
| Gate | ≤ 180 s |

O gate temporal está aprovado antes da abertura dos labels.

## Artefatos autoritativos

- Bundle combinado: `casos/qualification/openswisshcc_v1/runs/dev_v15_blind_fusion87/`
- Protocolo: `casos/qualification/openswisshcc_v1/prepared/development_freezes_v15/fusion_evaluation_protocol.json`
- Implementação: `dtwin/benchmark/openswisshcc_v15_fusion.py`
- Build cego: `tools/build_openswisshcc_v15_blind_fusion.py`
- Congelamento: `tools/freeze_openswisshcc_v15_fusion.py`
- Avaliação protegida: `tools/evaluate_openswisshcc_v15_fusion.py`
- Testes: `tests/test_openswisshcc_v15_fusion.py`

## Integridade criptográfica

- Assinatura interna do protocolo: `7e3914c332a1a997234e89e2e10a19625764fbd4e8437a58df30477adf66621e`
- SHA-256 do protocolo: `1C7F696757009546188F82076B1FB8704DAA78541A816FBDD62A1233609FDB21`
- SHA-256 do resumo do bundle: `2BDC15A14C7D4A05137DFD290553743422ADE957F67E05B18ABCEB281335A47B`
- SHA-256 dos sinais cegos: `A8BE855D1ADB7497CC31C4161CF15953E288D1025C64EFA31F7E59E89BAF4DA6`
- SHA-256 da implementação: `0AAB3BAADDC8D4EC33B37AC6203B0637B47826F8FBAAC4D371CD15D448800AD6`
- SHA-256 dos testes: `24B2B51C6B85AEBADB2050DE7B12A3733CB727209897DD373C30057DDCC81285`

## Testes executados

- testes v15 direcionados: 10 aprovados;
- suíte completa do ARGOS: 597 aprovados;
- falhas: 0;
- avisos: 334, sem novo erro bloqueante.

Os testes cobrem autorização obrigatória antes da leitura dos labels, adulteração de hash e assinatura, vazamento de campos protegidos, duplicação de casos, fitting exclusivo no treino, `INCONCLUSIVA` como erro e publicação atômica.

## Estado de segurança

No momento do congelamento:

- `ground_truth_read=false`;
- `metrics_calculated=false`;
- `holdout_opened=false`;
- `research_only=true`;
- `clinical_use_allowed=false`;
- `requires_human_review=true`.

## Próximo passo

É necessária autorização humana específica para abrir `development_labels.jsonl` exclusivamente no protocolo v15 assinado acima. A autorização não inclui o holdout.

Após autorização, o comando controlado será:

```powershell
.\.venv-win\Scripts\python.exe -B tools/evaluate_openswisshcc_v15_fusion.py `
  --bundle-root casos/qualification/openswisshcc_v1/runs/dev_v15_blind_fusion87 `
  --protocol casos/qualification/openswisshcc_v1/prepared/development_freezes_v15/fusion_evaluation_protocol.json `
  --development-labels casos/qualification/openswisshcc_v1/prepared/development_v1/protected_ground_truth/development_labels.jsonl `
  --output-dir casos/qualification/openswisshcc_v1/evaluations/dev_v15_fusion87 `
  --allow-protected-development-labels
```

O resultado deve ser aceito mesmo se contrariar a hipótese. Nenhum peso, feature, limiar, seed ou critério poderá ser alterado depois da avaliação.
