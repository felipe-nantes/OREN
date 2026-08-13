# 221 — Volumetria adaptativa e apresentação no visualizador

## Estado

As Fases 3 a 8 do plano de volumetria foram implementadas em 11 de agosto de
2026. A solução está integrada ao exame individual em modo de pesquisa e não
altera o volume, a máscara nem os painéis consumidos pelo classificador.

O resultado é uma medição física auditável da segmentação automática, com
fallback seguro, indicador de consistência técnica e apresentação no
visualizador 3D. Isso não é uma alegação de acurácia anatômica clínica.

## Fase 3 — segmentação adaptativa

O adaptador `dtwin/segmentation_shadow.py` mantém a fase arterial registrada
como fonte principal. A confirmação secundária só é acionada quando controles
label-blind identificam fallback, fragmentação, contato com a borda ou razão
volumétrica fora de 0,82–1,30 contra a máscara basal independente.

A ordem secundária é tardia, venosa e volume de referência. A expansão é aceita
somente até 12 mm da máscara principal, limitada a 18% do volume principal e sem
criar novo contato com a borda. Depois da fusão são aplicados preenchimento de
cavidades e retenção do maior componente.

Se a segunda segmentação falhar, exceder o tempo, não produzir máscara ou violar
um gate, a máscara principal válida é preservada. O exame não falha por causa da
confirmação opcional.

## Fase 4 — qualidade e faixa técnica

O manifesto volumétrico publica nota técnica A–D, razões objetivas, Dice e
Jaccard entre fontes, faixa mínima–máxima, dispersão percentual e a fonte final.
A faixa não é intervalo de confiança: mostra somente a variação entre máscaras
automáticas disponíveis para o exame.

## Fase 5 — estruturas

O motor calcula volume e percentual hepático de toda máscara publicada:
fígado, candidato não confirmado, região classificada, vasos, vesícula e
segmentos. Couinaud só é liberado quando os oito segmentos cobrem exatamente o
fígado, sem lacunas, sobreposição ou voxels externos. Não há preenchimento
artificial de regiões sem rótulo.

## Fase 6 — visualizador

A seção `Volumetria hepática` apresenta volume total, nota técnica, faixa entre
máscaras, volumes das estruturas, percentual hepático, seleção no 3D, gate de
Couinaud e downloads JSON/CSV. O navegador não recalcula medidas.

## Fase 7 — verificação

Verificador independente:

```powershell
python -m tools.verify_volumetry <pasta-outputs> --out <recibo.json>
```

Ele revalida schema, contrato, hash do CSV, unicidade das estruturas, igualdade
entre contagem física de voxels e volume e coerência do gate Couinaud.

### Smoke real

Caso `c2424a1dd2e1`, sem nova inferência do classificador:

- volume hepático: **1002,115 mL**;
- estruturas medidas: **14**;
- verificação independente: **aprovada**;
- hash do manifesto: `646169c06dfa0714d11c0614af6c3c0c0927bd08f4db00e6691463199b4e2e43`;
- hash do CSV: `446718223ac0040d766dc622e5415f377d557098307cd7f2c0ed504fa62a5af6`;
- qualidade: **B**, pois o caso antigo possui uma máscara no recibo;
- Couinaud: gate reprovado corretamente, cobertura 88,4489%, 22.955 voxels
  hepáticos ausentes e 5.464 voxels segmentares externos.

O gate evitou publicar volumes segmentares incompletos como se formassem 100%
do fígado.

## Fase 8 — integração e política

O cenário aprimorado é o padrão de pesquisa quando o MRSegmentator está
disponível. A seleção permanece restrita à configuração versionada. O navegador
não envia backend, executável, fase ou caminho arbitrário.

Proteções preservadas:

- `mask_organ.nii.gz`, `volume.nii.gz`, painéis e relatório são imutáveis;
- a máscara adaptativa alimenta somente 3D e volumetria;
- falha retorna para a máscara existente;
- revisão humana e aviso de pesquisa permanecem obrigatórios.

## Evidência e limite científico

No benchmark LiverHccSeg, a fusão registrada protegida obteve mediana Dice
0,9444, ASSD 1,994 mm, HD95 7,366 mm e razão volumétrica 0,9995. Quatro fases
excederam 180 segundos em parte dos casos; por isso não foram promovidas
integralmente ao webapp.

O modo adaptativo usa uma fase principal e confirmação condicional para preservar
o orçamento. Está tecnicamente pronto e protegido por fallback. Qualquer ganho
de acurácia em nova coorte deve ser declarado somente após comparação cega com
máscaras humanas.

## Arquivos principais

```text
dtwin/segmentation_shadow.py
dtwin/volumetry.py
dtwin/stages.py
webapp/server.py
viewer/index.html
viewer/app.js
viewer/argos-viewer.css
tools/verify_volumetry.py
configs/segmentation_visualization_v2.yaml
```
