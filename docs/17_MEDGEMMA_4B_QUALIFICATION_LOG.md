# Diário complementar — Qualificação MedGemma 4B

Este arquivo continua o registro de
`docs/17_MEDGEMMA_4B_QUALIFICATION.md`. Ele foi separado temporariamente porque o
arquivo original ficou associado a uma sandbox anterior e não pôde ser alterado
pelo editor seguro. Nenhum registro anterior foi removido.

## 2026-07-13 — Segmentação compartilhada no Windows

O primeiro piloto backend com dois negativos falhou antes da inferência. O
TotalSegmentator/nnU-Net encerrou workers com `WinError 6714`; portanto, qualquer
métrica daquela execução era tecnicamente inválida.

Alterações:

- criado `dtwin/seg_worker.py`, um worker mínimo e independente;
- criado `dtwin/segmentation_subprocess.py`, que executa uma cópia do worker em
  diretório temporário;
- benchmark CLI/backend e webapp passaram a usar o mesmo helper;
- parâmetros de task, modo rápido e dispositivo permanecem explícitos;
- staging e arquivos temporários continuam sendo removidos mesmo em falha.

Validação:

- 48 testes relacionados passaram;
- dois casos seguintes completaram segmentação e inferência, sem falha técnica;
- tempos totais: 28,83 s e 26,78 s;
- esta correção resolve estabilidade e comparabilidade, não acurácia.

## 2026-07-13 — Estratégias de resposta curta avaliadas

### JSON compacto livre — descartado

- com 256 tokens, o modelo consumiu a janela em raciocínio e não iniciou JSON;
- tempo observado: 19,3 s;
- com prefixo causal `{` e exemplo, copiou placeholders do exemplo em 10,2 s;
- sem exemplo, copiou uma instrução como evidência em cerca de 12 s;
- descartado: JSON válido não demonstrou evidência clínica válida.

### Pontuação fechada A/B/C — descartada para decisão clínica

- rótulos por extenso tinham números diferentes de tokens;
- códigos A/B/C ainda mostraram preferência posicional;
- contrabalanceamento por quadrado latino gerou, em um negativo: positiva 0,344,
  negativa 0,330 e inconclusiva 0,325;
- dois negativos tecnicamente válidos foram classificados como positivos;
- especificidade provisória: 0/2;
- descartado: escolher um limiar nesses casos esconderia o viés em vez de validar
  capacidade clínica.

### Rótulo JSON predefinido — candidato técnico atual

- o gateway usa o prefixo causal `{"resultado_hipotese":"`;
- o modelo completa classe, confiança e revisão humana obrigatória;
- o cliente aceita somente o objeto mínimo ou exatamente esses três campos;
- qualquer quarta chave ou inconsistência invalida a saída;
- a resposta é expandida deterministicamente ao schema legado, sem inventar
  localização, achado ou diagnóstico;
- 64 tokens foram necessários para fechar o JSON; 16 eram insuficientes;
- geração observada: aproximadamente 2,3–2,8 s.

Resultado provisório:

- dois negativos preparados foram classificados `POSITIVA/alta`;
- o objetivo temporal foi atendido no piloto, mas a especificidade não;
- o modo permanece restrito à qualificação.

## 2026-07-13 — Painel recortado no fígado

Hipótese: o fígado ocupava poucos pixels e o contorno amarelo poderia parecer uma
alteração focal.

Alterações:

- adicionado `panel.crop_to_liver` e margem relativa configurável;
- recorte consistente por orientação a partir da projeção da máscara;
- adicionado `overlay_mode=none`, permitido apenas com recorte ativo;
- manifesto registra modo de evidência, margem e overlay;
- o painel baseline foi preservado;
- modos uniforme e volumétrico continuam suportados.

Validação:

- 70 testes relacionados passaram;
- o teste de imagem confirma ausência do contorno amarelo;
- em um negativo: painel 0,25 s, modelo 2,77 s, triagem 3,12 s;
- o resultado ainda foi `POSITIVA/alta`;
- conclusão: o recorte melhora pixels úteis e latência, mas o contorno não era a
  causa principal do falso positivo.

## Estado atual

| Critério | Estado | Evidência |
|---|---|---|
| análise abaixo de 180 s | atingido no piloto | 27–29 s com segmentação; ~3 s preparado |
| backend sem falha de segmentação | atingido no piloto | 2/2 casos completaram |
| sensibilidade ≥ 75% | ainda não medida com validade | piloto positivo pendente |
| especificidade ≥ 75% | não atingida | 0/2 negativos |
| benchmark publicável | não atingido | lotes locais têm confundimento de protocolo |

Próxima etapa:

- executar um piloto balanceado com a mesma configuração;
- estratificar por sequência/protocolo;
- avaliar evidência visual por sequência/fase;
- não congelar limiares ou prompt com base em dois negativos.
