# OpenSwissHCC v10 — localizador MR e painéis ROI

Data: 15 de julho de 2026  
Uso: pesquisa, com revisão humana obrigatória

## Objetivo

O v9 provou que a cobertura T1/T2/TRACE/ADC e o tempo estavam corretos, mas os
scores pairwise do MedGemma 4B tinham AUC máxima de apenas 0,565. O v10 muda a
fonte de evidência: um modelo público 3D propõe regiões candidatas e o MedGemma
4B será usado posteriormente para rejeitar mimetizadores e falsos positivos.

O localizador não emite diagnóstico e não é uma decisão final.

## Localizador

- software: TotalSegmentator 2.15.0;
- task: `liver_lesions_mr`;
- pesos: Dataset589, fold 0;
- treinamento declarado nos metadados locais: 750 volumes MR;
- entrada: T1 venoso;
- recorte: máscara hepática venosa;
- resolução-alvo do modelo: aproximadamente 0,86 × 0,86 × 1,0 mm;
- limite do estágio: 90 segundos por caso;
- máscara de lesão do OpenSwissHCC: proibida.

O runner valida SHA-256 e bytes do T1 e da máscara hepática, rejeita qualquer
role/path que contenha `lesion`, restringe a saída ao fígado e persiste apenas
features e máscaras candidatas derivadas do modelo. `ground_truth_read` e
`final_decision` permanecem falsos/nulos.

## Particularidade do Windows

Nesta máquina, `python -m` faz os workers `multiprocessing.spawn` herdarem um
contexto transacional inválido do executor, resultando em `WinError 6714` ao
importar `pyarrow`. A inicialização `python -c` não apresenta esse problema e
foi validada em execuções reais.

Launcher:

```powershell
powershell -ExecutionPolicy Bypass -File tools/run_openswisshcc_lesion_localizer_pilot_win.ps1
```

O erro operacional foi testado três vezes e todas as tentativas abortaram sem
publicar destino ou staging parcial.

## Piloto técnico

Um caso independente concluiu em 28,65 s. A máscara tinha geometria idêntica ao
T1, um componente de 82 voxels, cerca de 347 mm³, e zero voxel fora do fígado.

## Piloto determinístico de dez casos

A seleção foi definida pela ordem SHA-256 do plano cego assinado v9, sem consulta
a labels.

- casos: 10/10;
- falhas: 0;
- média: 23,58 s;
- máximo: 28,19 s;
- candidatos presentes: 9;
- sem candidato: 1;
- ground truth/máscara de lesão durante a localização: não;
- decisão final: não.

Após persistir todos os artefatos, os labels de desenvolvimento foram anexados
para análise exploratória:

- composição: 4 positivos e 6 negativos;
- presença de candidato: sensibilidade 100%, especificidade 16,7%;
- AUC do volume candidato total: 0,75;
- volume candidato médio: 2.922 mm³ nos positivos e 2.182 mm³ nos negativos.

O localizador é sensível, mas não específico. Ele não pode substituir o
MedGemma ou a revisão humana. O AUC exploratório, porém, superou o v9 e justifica
testar ROIs ampliadas.

## Painéis ROI morfológicos

Foram gerados até três painéis por caso para os maiores componentes. Cada painel
2×2 mostra o mesmo centro físico em:

1. T1 venoso;
2. T2 nativo;
3. último TRACE ordenado disponível;
4. ADC nativo.

O T1 mostra em amarelo apenas o contorno derivado do localizador. O texto do tile
declara explicitamente `candidato do localizador, não GT`. Casos sem candidato
recebem um fallback centrado no fígado, sem contorno.

Galeria original preservada:

```text
casos/qualification/openswisshcc_v1/prepared/
development_review_gallery_v10_localizer_roi_pilot10/index.html
```

- 10 casos;
- 27 painéis;
- assinatura: `bc8e99ba916df250c8f9db7a82b199ab0a8a42715fbba5dc2424912f1c662399`;
- painéis fora dos limites: 0;
- vazamentos de label/subject/diagnóstico: 0;
- inferência MedGemma executada: não.

## Correção do fallback sem candidato

Durante a revisão humana, o item 7 (`anon-openswiss-d57d150734a23acd`) foi
questionado por não exibir contorno amarelo. A auditoria confirmou que não houve
corte do crop: o localizador não produziu candidato nesse caso. O painel era um
fallback deliberado no centro hepático.

Para remover a ambiguidade, o gerador passou a registrar e exibir:

- `fallback_no_candidate=true`;
- `fallback_reason=no_model_derived_candidate`;
- texto `SEM CANDIDATO - FALLBACK NO CENTRO HEPATICO` em todos os tiles.

A galeria original foi preservada e uma versão nova foi publicada:

```text
casos/qualification/openswisshcc_v1/prepared/
development_review_gallery_v10_localizer_roi_pilot10_v2/index.html
```

- casos: 10;
- painéis: 27;
- assinatura: `9b3ea1bd746fdc4364a586569f46a5e7db78240c9ff1369171954cace6d3946a`;
- erros de hash, bytes, flags e anonimização: 0.

## Painéis ROI de realce dinâmico

Foi criada uma segunda galeria com o mesmo centro físico em:

1. T1 nativo;
2. T1 arterial registrado;
3. T1 venoso;
4. T1 tardio registrado.

```text
casos/qualification/openswisshcc_v1/prepared/
development_review_gallery_v10_localizer_enhancement_roi_pilot10/index.html
```

- casos: 10;
- painéis: 27;
- assinatura: `a92f387de95a11030ff61248b733e8f9b395b8d44adf38359c74e94e3ab3d8ce`;
- erros de hash, bytes, flags e anonimização: 0;
- tiles indisponíveis: 3, todos T1 tardio registrado do caso
  `anon-openswiss-2366eaabe35a78c3`, por `sem_contraste_no_roi`;
- cada um desses painéis preserva três fases utilizáveis.

Uma fase dentro do FOV, porém sem contraste útil, vira placeholder explícito.
Nenhum pixel é sintetizado. O painel aborta atomicamente se o T1 venoso estiver
inválido ou se houver menos de duas fases utilizáveis.

## Validação automatizada

Após as mudanças:

- testes focados: 6 aprovados;
- suíte completa: **487 aprovados**, sem falhas;
- hashes e bytes dos 54 painéis: válidos;
- IDs não anonimizados: 0;
- leitura de ground truth de lesão: não;
- inferência MedGemma: não.

## Gate humano pendente

Antes de chamar o MedGemma 4B, revisar:

- o centro do contorno amarelo está realmente no fígado;
- os quatro tiles mostram a mesma região anatômica aproximada;
- o crop não corta completamente a região candidata;
- contraste e resolução permitem avaliar a região;
- tiles indisponíveis estão explicitamente marcados e não foram sintetizados;
- não há PHI;
- o fallback sem candidato mostra fígado reconhecível.

Somente após aprovação humana das duas galerias será criado um freeze de
prompt/ROIs e executada a inferência 4B scores-only. O holdout permanece fechado.
