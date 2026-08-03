# Ingestão de DICOM bruto multifásico

**Estado:** implementado em 2 de agosto de 2026  
**Uso:** pesquisa com revisão humana obrigatória

## Objetivo

O exame individual do ARGOS aceita agora a pasta bruta exportada do equipamento
ou PACS. O usuário não precisa renomear manualmente as séries como `arterial`,
`venous` e `delayed`.

## Ordem de resolução

1. Pastas explicitamente nomeadas continuam tendo prioridade e confiança 100%.
2. Sem essas pastas, o ARGOS agrupa os arquivos por Study/Series Instance UID.
3. Procura primeiro semântica inequívoca nos campos técnicos:
   `SeriesDescription`, `ProtocolName`, `SequenceName` e `ImageType`.
4. Na ausência de nomes explícitos, aceita um único conjunto de séries T1 axiais
   pós-contraste, temporalmente ordenável:
   - primeira série: arterial;
   - segunda série: portal/venosa;
   - última série: tardia.
5. As séries selecionadas são materializadas em uma área interna do job e o
   pipeline multifásico existente segue sem alteração.

Reconstruções derivadas de subtração, MPR e MIP são excluídas da resolução
temporal. Elas frequentemente repetem horário e protocolo da aquisição original
e, se tratadas como uma nova fase, tornam a ordem artificialmente ambígua.
Quando pelo menos três séries registram `ContrastBolusAgent`, elas têm prioridade
sobre descrições genéricas como `PRE-POST`. Séries in-phase e opposed-phase não
participam da resolução dinâmica.

Nos DICOMs clássicos, os cortes são ordenados pela posição física projetada na
normal registrada em `ImageOrientationPatient`/`ImagePositionPatient`. Ordenar
por nome de arquivo pode inverter o eixo Z (`1-10` antes de `1-2`) e foi
explicitamente eliminado. `InstanceNumber` é usado somente quando a posição
física não estiver disponível.

## Condições de recusa

O resolvedor falha sem produzir classificação quando:

- há mais de um estudo elegível no envio;
- faltam três séries dinâmicas;
- séries possuem horários/números repetidos ou ausentes;
- geometria ou orientação são incompatíveis;
- os metadados não demonstram T1 pós-contraste;
- pastas nomeadas foram fornecidas parcialmente ou de forma ambígua.

Não há fallback para uma série aleatória e nenhuma fase é inventada.

## Auditoria e PHI

O arquivo `phase_resolution_manifest.json` registra:

- método e confiança da resolução;
- hashes dos UIDs do estudo e das séries;
- número de arquivos e frames;
- número técnico da série e orientação;
- papel atribuído a cada série.

Nome do paciente, Patient ID, descrições livres e UIDs brutos não são
persistidos. O resultado do frontend mostra a origem da resolução das fases.

## Uso no frontend

1. Abra **Exame individual**.
2. Clique em **Selecionar pasta**.
3. Escolha a raiz do estudo exportado, mesmo que contenha muitas subpastas.
4. O ARGOS enviará todos os arquivos preservando seus caminhos relativos.
5. Se as fases forem ambíguas, a mensagem informará que a identificação segura
   não foi possível; o exame não seguirá para segmentação ou classificação.

## Limite metodológico

A ordem temporal é uma inferência técnica reproduzível, não uma garantia clínica
universal. Protocolos atípicos, séries repetidas ou fases intermediárias podem
exigir confirmação humana. Por isso o método aparece no resultado com confiança
de 80%, e a pasta explicitamente curada continua sendo a referência de 100%.

## Smoke test real

O caso bruto TCGA-BC-A216 foi enviado com 619 arquivos e 12 séries, sem pastas de
fase. O resolvedor selecionou as séries 9, 10 e 12; arterial, venosa e tardia
cobriram 100% da mesma grade. O fluxo completo terminou em 83,5 segundos, com
segmentação plausível, três painéis, classificação e visualizador 3D disponível.
## Validação pareada da resolução automática

Antes de comparar a acurácia entre pastas de fases já organizadas e um envio
DICOM bruto, o ARGOS gera uma galeria técnica cega com os mesmos níveis axiais
nas fases arterial, venosa e tardia. A galeria não lê labels nem máscaras de
lesão. Ela registra o método de resolução, números e hashes das séries, janela
comum por caso, cobertura após harmonização e exclusões técnicas.

```powershell
python tools/build_raw_phase_review_gallery.py `
  --labels casos/qualification/tcga_positive_stress/labels.yaml `
  --source-root "C:/Users/profurg/Desktop/sander/dicoms/lote 1" `
  --source-root "C:/Users/profurg/Desktop/sander/dicoms/lote 2" `
  --source-root "C:/Users/profurg/Desktop/sander/dicoms/lote 3" `
  --out casos/qualification/tcga_positive_stress/raw_phase_review_v1
```

Somente depois da aprovação humana dessa galeria as inferências pareadas podem
ser executadas. Um conjunto negativo multifásico rotulado continua obrigatório
para medir especificidade; uma coorte exclusivamente positiva mede apenas
sensibilidade, taxa de conclusão, tempo e discordância entre os dois caminhos.

O executor retomável `tools/run_raw_phase_equivalence_benchmark.py` resegmenta a
fase venosa em resolução completa, gera painéis por resolução automática e por
mapeamento explícito aprovado e exige igualdade byte a byte antes de reutilizar
a inferência. Falhas técnicas contam como falsos negativos. Os labels públicos
são abertos somente depois de todas as predições terem sido persistidas.
