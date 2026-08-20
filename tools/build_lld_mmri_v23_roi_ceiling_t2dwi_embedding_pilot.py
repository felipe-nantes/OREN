"""T2/DWI captado por EMBEDDING eleva o teto de discriminacao de subtipo?

A lacuna que este piloto fecha, em uma frase: docs/142 testou T2/DWI no mesmo
local fisico da lesao e falhou (+0,23 ponto, ruido), mas com DESCRITORES
ARTESANAIS -- razao de intensidade mediana e IQR. docs/143, logo depois, trocou
descritores artesanais por EMBEDDING MedSigLIP para a dinamica e saltou de
74,47% para 79,49% (+5,02). Ninguem testou a combinacao: T2/DWI por embedding.

Um padrao espacial -- cicatriz central de FNH, textura de restricao a difusao --
e' exatamente o que um embedding capta e uma mediana de intensidade apaga. Se
T2/DWI carrega sinal complementar de subtipo, e' por essa via que ele aparece.

METODO -- identico ao braco B de docs/143 em tudo, exceto a fonte dos canais:
  mesma ROI de ground truth, mesma margem, mesmos cortes axiais, mesmo tile,
  mesmos splits congelados, mesmo estimador. A UNICA variavel e' o conteudo dos
  canais RGB. Isso e' o que torna a comparacao contra 79,49% legitima.

T2 e DWI vivem em grades nativas diferentes da venosa (7 mm de corte contra
3 mm). Sao reamostrados na grade venosa por transformacao de identidade em
coordenadas fisicas -- a mesma tecnica de producao
(dtwin/benchmark/lld_mmri_v23_harmonization.py::_harmonize). Isso corrige
descasamento de grade, NAO movimento respiratorio, e nao recupera detalhe
atraves do plano que a aquisicao nao capturou.

BRACOS:
  B) embedding do recorte dinamico            (referencia ja medida: 79,49%)
  T) embedding do recorte T2/DWI sozinho       (diagnostico: ha sinal?)
  E) concatenacao B+T + indicador de ausencia  (a hipotese)

GATE PRE-ESPECIFICADO, ESCRITO ANTES DE QUALQUER NUMERO:
  primario: balanceada do braco E >= 81,49%  (79,49% + 2,00 pontos)

A margem de 2 pontos e' menor que o salto de +5,02 que a troca
artesanal->embedding deu para a dinamica, porque aqui T2/DWI e' sinal
COMPLEMENTAR a uma representacao que ja funciona, nao substituto de uma que
falhava. Se falhar, a linha para e o resultado negativo e' documentado --
nao se afrouxa o gate depois de ver o numero.

RESSALVAS QUE ACOMPANHAM QUALQUER RESULTADO DESTE SCRIPT:
  - ROI de ground truth e' TETO, nao desempenho. Mede discriminacao dado que a
    lesao foi perfeitamente localizada; o efetivo exige multiplicar pelo recall
    do localizador (~80%, docs/141).
  - Mascara de lesao usada SO' para definir o recorte, na avaliacao, nunca como
    entrada do modelo e nunca em inferencia.
  - LLD-MMRI nao possui mapa ADC. Este piloto usa T2 e DWI reais; nao ha
    terceiro sinal de difusao a acrescentar.
"""
from __future__ import annotations

import json
import time
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import SimpleITK as sitk

warnings.filterwarnings("ignore")

from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dtwin.learning.medsiglip_multiclass_classifier import (
    build_multiclass_labels,
)
from dtwin.learning.protocol import (
    load_protected_cases,
    load_protected_label_rows,
)
from dtwin.learning.robustness import clinical_subtype_map

REPO = Path(".").resolve()
CFG = REPO / "configs/training/hybrid_v1_protocol.yaml"
SPLITS = REPO / "configs/training/hybrid_v1_nested_splits.json"
EMBED_CFG = REPO / "configs/training/medsiglip_frozen_v1.yaml"
HARM = REPO / "casos/qualification/lld_mmri_v23/prepared/external_dynamic_harmonized_v1/cases"
INPUTS = REPO / "casos/qualification/lld_mmri_v23/prepared/external_inputs_v1/inputs"
MAPPING = REPO / "casos/qualification/lld_mmri_v23/prepared/external_protocol_v1/protected_source/mapping.jsonl"
GT = REPO / "casos/qualification/lld_mmri_v23/lesion_masks_cv_v1"
CACHE_DYN = REPO / "casos/qualification/hybrid_v1/crop_embeddings_v1"
CACHE_T2DWI = REPO / "casos/qualification/hybrid_v1/crop_embeddings_t2dwi_v1"
OUT = REPO / "casos/qualification/hybrid_v1/roi_ceiling_t2dwi_embedding_v1"

SUBTYPES = ["fnh", "hcc", "hemangioma", "hepatic_cyst"]
SEED = 20260724

# Geometria de recorte -- IDENTICA a docs/143. Nao alterar sem invalidar a
# comparabilidade com o braco B de referencia.
MARGIN = 0.35
TILE = 448
N_SLICES = 3

BASELINE_B = 0.7949           # docs/143, braco B
GATE_MARGIN = 0.02            # +2 pontos
GATE_BALANCED = BASELINE_B + GATE_MARGIN

MIN_COVERAGE = 0.90           # cobertura minima da caixa de recorte por T2/DWI

log: list[str] = []


def say(text: str = "") -> None:
    print(text, flush=True)
    log.append(text)


def window(array: np.ndarray) -> np.ndarray:
    """Janela robusta por percentil sobre voxels nao nulos (identica a docs/143)."""
    nonzero = array[array > 0]
    if nonzero.size < 10:
        return np.zeros_like(array)
    low, high = np.percentile(nonzero, [2.0, 98.0])
    if high <= low:
        return np.zeros_like(array)
    return np.clip((array - low) / (high - low), 0.0, 1.0)


def resample_to_reference(moving: sitk.Image, reference: sitk.Image) -> tuple[np.ndarray, np.ndarray]:
    """Reamostra na grade de referencia por identidade fisica; devolve volume e suporte.

    Identidade e' deliberado, nao uma simplificacao: preserva a posicao fisica
    que o scanner gravou, que e' a mesma convencao usada para construir os dados
    de treino da dinamica. Corrige descasamento de grade, nao movimento.
    """
    identity = sitk.Transform(3, sitk.sitkIdentity)
    resampled = sitk.Resample(
        sitk.Cast(moving, sitk.sitkFloat32), reference, identity,
        sitk.sitkLinear, 0.0, sitk.sitkFloat32,
    )
    support_source = sitk.Image(moving.GetSize(), sitk.sitkUInt8) + 1
    support_source.CopyInformation(moving)
    support = sitk.Resample(
        support_source, reference, identity, sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8,
    )
    return (
        sitk.GetArrayFromImage(resampled).astype(np.float32),
        sitk.GetArrayFromImage(support) > 0,
    )


def crop_geometry(mask: np.ndarray) -> tuple[list[int], int, int, int, int] | None:
    """Caixa quadrada com margem e cortes axiais -- identica a docs/143."""
    if int(mask.sum()) < 10:
        return None
    zs, ys, xs = np.where(mask)
    z0, z1 = int(zs.min()), int(zs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    center_y, center_x = (y0 + y1) / 2.0, (x0 + x1) / 2.0
    half = max(y1 - y0, x1 - x0) / 2.0 * (1.0 + MARGIN)
    half = max(half, 12.0)
    height, width = mask.shape[1], mask.shape[2]
    ya, yb = max(0, int(center_y - half)), min(height, int(center_y + half) + 1)
    xa, xb = max(0, int(center_x - half)), min(width, int(center_x + half) + 1)
    span = z1 - z0
    if span == 0:
        z_indices = [z0]
    else:
        z_indices = sorted({int(round(z0 + f * span)) for f in (0.25, 0.5, 0.75)})
    return z_indices[:N_SLICES], ya, yb, xa, xb


def build_t2dwi_panels(case_id: str, subject: dict[str, str]) -> tuple[list[Image.Image], float] | None:
    """Recorte RGB de T2/DWI na MESMA caixa fisica da lesao.

    Mapeamento de canal R=T2, G=DWI, B=DWI: o LLD-MMRI nao tem mapa ADC, entao
    ha' dois sinais reais para tres canais. Duplicar o DWI concentra a capacidade
    no sinal de restricao a difusao, que e' o mais associado a hipotese clinica
    sob teste. E' uma escolha, nao um fato -- esta' registrada no results.json.
    """
    gt_path = GT / f"{subject[case_id]}_C+V.nii.gz"
    if not gt_path.exists():
        return None
    mask = sitk.GetArrayFromImage(sitk.ReadImage(str(gt_path))) > 0
    geometry = crop_geometry(mask)
    if geometry is None:
        return None
    z_indices, ya, yb, xa, xb = geometry

    reference_path = HARM / case_id / "t1_venous.nii.gz"
    if not reference_path.is_file():
        return None
    reference = sitk.ReadImage(str(reference_path))
    if mask.shape != sitk.GetArrayFromImage(reference).shape:
        return None

    volumes: dict[str, np.ndarray] = {}
    supports: dict[str, np.ndarray] = {}
    for role in ("t2", "dwi"):
        source_path = INPUTS / case_id / f"{role}.nii.gz"
        if not source_path.is_file():
            return None
        volume, support = resample_to_reference(sitk.ReadImage(str(source_path)), reference)
        volumes[role] = window(volume)
        supports[role] = support

    box = np.zeros(mask.shape, dtype=bool)
    box[min(z_indices):max(z_indices) + 1, ya:yb, xa:xb] = True
    box_voxels = int(box.sum())
    if box_voxels <= 0:
        return None
    coverage = min(
        float(np.count_nonzero(box & supports[role])) / float(box_voxels)
        for role in ("t2", "dwi")
    )
    if coverage < MIN_COVERAGE:
        return None

    images: list[Image.Image] = []
    for z in z_indices:
        rgb = np.stack(
            [volumes["t2"][z, ya:yb, xa:xb],
             volumes["dwi"][z, ya:yb, xa:xb],
             volumes["dwi"][z, ya:yb, xa:xb]],
            axis=-1,
        )
        if rgb.shape[0] < 4 or rgb.shape[1] < 4:
            continue
        image = Image.fromarray((np.flipud(rgb) * 255).astype(np.uint8), mode="RGB")
        images.append(image.resize((TILE, TILE), Image.Resampling.BILINEAR))
    return (images, coverage) if images else None


def main() -> int:
    say("=" * 78)
    say("TETO COM EMBEDDING DE T2/DWI NO MESMO RECORTE DA LESAO")
    say("=" * 78)
    say(f"gate pre-especificado: balanceada do braco E >= {100*GATE_BALANCED:.2f}%")
    say(f"  (referencia docs/143 braco B = {100*BASELINE_B:.2f}%, margem +{100*GATE_MARGIN:.2f})")
    say()

    cases = load_protected_cases(CFG, REPO)
    by_case, _ = build_multiclass_labels(
        cases, clinical_subtype_map(load_protected_label_rows(CFG, REPO))
    )
    subject = {}
    for line in MAPPING.open(encoding="utf-8"):
        row = json.loads(line)
        subject[row["case_id"]] = row["source_subject_id"]
    targets = sorted(c.case_id for c in cases if by_case.get(c.case_id) in SUBTYPES)
    say(f"casos alvo: {len(targets)}")

    dynamic: dict[str, np.ndarray] = {}
    for case_id in targets:
        path = CACHE_DYN / f"{case_id}.npy"
        if path.exists():
            dynamic[case_id] = np.load(path).astype(np.float64)
    say(f"embeddings dinamicos em cache (braco B): {len(dynamic)}")

    CACHE_T2DWI.mkdir(parents=True, exist_ok=True)
    t2dwi: dict[str, np.ndarray] = {}
    coverages: dict[str, float] = {}
    pending = []
    for case_id in targets:
        path = CACHE_T2DWI / f"{case_id}.npy"
        if path.exists():
            t2dwi[case_id] = np.load(path).astype(np.float64)
        else:
            pending.append(case_id)

    insufficient: list[str] = []
    if pending:
        say(f"embutindo recortes T2/DWI de {len(pending)} casos...")
        from dtwin.learning.medsiglip_embeddings import (
            HuggingFaceMedSigLIPBackend,
            load_embedding_config,
        )
        backend = HuggingFaceMedSigLIPBackend(load_embedding_config(EMBED_CFG))
        started = time.time()
        try:
            for index, case_id in enumerate(pending, start=1):
                try:
                    built = build_t2dwi_panels(case_id, subject)
                    if built is None:
                        insufficient.append(case_id)
                        continue
                    images, coverage = built
                    vectors = backend.embed(images)
                    mean = vectors.mean(axis=0)
                    mean = mean / max(float(np.linalg.norm(mean)), 1e-9)
                    np.save(CACHE_T2DWI / f"{case_id}.npy", mean.astype(np.float32))
                    t2dwi[case_id] = mean.astype(np.float64)
                    coverages[case_id] = coverage
                except Exception as exc:
                    say(f"  ! {case_id}: {type(exc).__name__}: {exc}")
                    insufficient.append(case_id)
                if index % 50 == 0 or index == len(pending):
                    say(f"  {index}/{len(pending)}  {(time.time()-started)/60:.1f}min  ok={len(t2dwi)}")
        finally:
            backend.close()
    say(f"casos com embedding T2/DWI: {len(t2dwi)}  (sem cobertura suficiente: {len(insufficient)})")
    say()

    splits = json.loads(SPLITS.read_text(encoding="utf-8"))
    label_index = {name: i for i, name in enumerate(SUBTYPES)}

    def run_arm(build_vector, pool, title, c_value=0.01):
        features, labels = {}, {}
        for case_id in pool:
            vector = build_vector(case_id)
            if vector is None:
                continue
            features[case_id] = vector
            labels[case_id] = label_index[by_case[case_id]]
        predictions = {}
        for outer in splits["outer_folds"]:
            train = [c for c in outer["train_case_ids"] if c in features]
            test = [c for c in outer["test_case_ids"] if c in features]
            if len(train) < 8 or not test:
                continue
            model = Pipeline([
                ("scaler", StandardScaler()),
                ("classifier", LogisticRegression(
                    C=c_value, class_weight="balanced", max_iter=5000, random_state=SEED)),
            ])
            model.fit(np.stack([features[c] for c in train]),
                      np.array([labels[c] for c in train]))
            classes = list(model.named_steps["classifier"].classes_)
            for case_id in test:
                probabilities = model.predict_proba(features[case_id][None, :])[0]
                predictions[case_id] = classes[int(np.argmax(probabilities))]
        matrix = {name: Counter() for name in SUBTYPES}
        for case_id, predicted in predictions.items():
            matrix[SUBTYPES[labels[case_id]]][SUBTYPES[predicted]] += 1
        recalls = {}
        for name in SUBTYPES:
            total = sum(matrix[name].values())
            recalls[name] = matrix[name][name] / total if total else 0.0
        balanced = sum(recalls.values()) / len(SUBTYPES)
        top1 = (sum(matrix[n][n] for n in SUBTYPES) / len(predictions)) if predictions else 0.0
        dimension = len(next(iter(features.values()))) if features else 0
        say(f"{title}  (n={len(predictions)}, dim={dimension})")
        say(f"   balanceada = {100*balanced:6.2f}%   top-1 = {100*top1:6.2f}%")
        say("   " + "  ".join(f"{n[:4]} {100*recalls[n]:.1f}%" for n in SUBTYPES))
        say()
        return {"balanced": balanced, "top1": top1, "recalls": recalls,
                "n": len(predictions), "dim": dimension,
                "confusion": {n: dict(matrix[n]) for n in SUBTYPES}}

    zero_t2dwi = np.zeros(1152, dtype=np.float64)

    def dynamic_vector(case_id):
        return dynamic.get(case_id)

    def t2dwi_vector(case_id):
        return t2dwi.get(case_id)

    def fused_vector(case_id):
        base = dynamic.get(case_id)
        if base is None:
            return None
        # Sinal ausente NAO remove o caso do denominador: entra zerado com um
        # indicador explicito, o mesmo padrao missing-aware de docs/183-184.
        extra = t2dwi.get(case_id)
        missing = extra is None
        return np.concatenate([base, zero_t2dwi if missing else extra, [1.0 if missing else 0.0]])

    pool = [c for c in targets if c in dynamic]
    say("-" * 78)
    say("ABLACAO")
    say("-" * 78)
    arm_b = run_arm(dynamic_vector, pool, "B) embedding do recorte dinamico (referencia)")
    arm_t = run_arm(t2dwi_vector, [c for c in pool if c in t2dwi],
                    "T) embedding do recorte T2/DWI sozinho (diagnostico)")
    arm_e = run_arm(fused_vector, pool, "E) dinamico + T2/DWI + indicador (hipotese)")

    say("=" * 78)
    say("GATE PRE-ESPECIFICADO")
    say("=" * 78)
    passed = arm_e["balanced"] >= GATE_BALANCED
    delta = arm_e["balanced"] - arm_b["balanced"]
    say(f"  braco E   : {100*arm_e['balanced']:.2f}%")
    say(f"  exigido   : {100*GATE_BALANCED:.2f}%  ({'PASSA' if passed else 'FALHA'})")
    say(f"  delta sobre o braco B medido aqui: {100*delta:+.2f} pontos")
    say(f"  braco T sozinho: {100*arm_t['balanced']:.2f}%  (acaso = 25,00%)")
    say()
    if not passed:
        say("  RESULTADO NEGATIVO. Pela pre-especificacao, a linha para aqui.")
        say("  Nao se afrouxa gate depois de ver o numero.")
    say("=" * 78)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps({
        "schema": "argos-roi-ceiling-t2dwi-embedding-v1",
        "question": "T2/DWI por embedding aprendido eleva o teto que descritores artesanais nao elevaram?",
        "crop": {"margin": MARGIN, "tile": TILE, "n_slices": N_SLICES,
                 "dynamic_channels": "R=arterial G=venous B=delayed",
                 "t2dwi_channels": "R=t2 G=dwi B=dwi",
                 "t2dwi_channel_choice_is_a_decision": True,
                 "adc_unavailable_in_lld_mmri": True},
        "resampling": {"method": "identity_physical_transform",
                       "corrects": "grid_mismatch_only_not_respiratory_motion",
                       "min_coverage": MIN_COVERAGE},
        "gate": {"baseline_arm_b": BASELINE_B, "margin": GATE_MARGIN,
                 "balanced_min": GATE_BALANCED, "passed": passed,
                 "prespecified_before_running": True},
        "arms": {"B_dynamic": arm_b, "T_t2dwi_only": arm_t, "E_fused": arm_e},
        "delta_e_minus_b": delta,
        "cases_without_sufficient_t2dwi": len(insufficient),
        "missing_signal_policy": "zero_vector_with_explicit_indicator_never_removed_from_denominator",
        "ceiling_not_performance": "ROI de ground truth; efetivo exige multiplicar pelo recall do localizador (~80%, docs/141)",
        "lesion_mask_used_for": "crop_definition_in_evaluation_only_never_model_input",
        "research_only": True, "clinical_use_allowed": False,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "log.txt").write_text("\n".join(log), encoding="utf-8")
    say(f"salvo em {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
