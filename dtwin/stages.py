#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dtwin.stages — Os sete estágios do pipeline, cada um com seu gate.

Filosofia (contexto/05_PIPELINE.md): cada estágio valida a própria entrada e
ABORTA com PipelineError se algo estiver errado. Nunca fabrica, nunca segue
mesmo assim. Cada estágio lê os artefatos do anterior em disco e grava os seus,
o que torna o pipeline resumível e testável estágio a estágio.

Fluxo:
  prepare  -> 1 ingestão+deid | 2 normalização | 3 órgão (auto) | 4a preparar lesão
  finalize -> 4b importar lesão | 5 refino | 6 malha | 7 STL + publicação
"""
from __future__ import annotations

import json
import logging
import shutil
import textwrap
import uuid
from pathlib import Path

import numpy as np
import pydicom
import pyvista as pv
import SimpleITK as sitk
from scipy import ndimage
from skimage import measure, morphology

from .core import (
    Case,
    PipelineError,
    array_from,
    array_to_image,
    now_utc,
    read_dicom_series,
    read_image,
    save_image,
    sha256_of,
    world_vertices_from_index,
)
from .viewer_artifacts import (
    acquisition_summary,
    compute_mesh_metrics,
    generate_reference_images,
    lesion_segment_overlap,
    nearest_surface_relationships,
)
from .segmentation_contract import approved_visualization_mask
from .volumetry import VolumetryStructure, build_volumetry_manifest
from .viewer_xr import build_xr_render_asset

log = logging.getLogger("dtwin")

MIN_SLICES = 3


# --------------------------------------------------------------------------- #
# Helpers internos
# --------------------------------------------------------------------------- #
def _first_dicom(folder: Path):
    files = [p for p in folder.rglob("*") if p.is_file()]
    pool = [p for p in files if p.suffix.lower() == ".dcm"] or files
    for p in pool:
        try:
            pydicom.dcmread(str(p), stop_before_pixels=True, force=True)
            return str(p)
        except Exception:  # noqa: BLE001
            continue
    return None


def _make_case_id(policy: str, ds) -> str:
    """Gera o identificador do caso conforme a política de privacidade.

    MVP usa 'anonymize' (UUID, sem vínculo com o paciente). 'pseudonymize' é um
    ponto de extensão RESERVADO (contexto/03_REGULATORIO_LGPD.md): exige um cofre
    de chaves protegido antes do uso clínico, por isso aqui aborta explicitamente
    em vez de simular um vínculo.
    """
    if policy == "anonymize":
        return "anon-" + uuid.uuid4().hex[:12]
    if policy == "pseudonymize":
        raise PipelineError(
            "Pseudonimização ainda não habilitada no MVP. O ponto de extensão "
            "existe (contexto/03_REGULATORIO_LGPD.md), mas exige um cofre de "
            "chaves protegido antes do uso clínico. Rode com --policy anonymize."
        )
    raise PipelineError(f"Política de privacidade desconhecida: {policy}")


def _archive_for_training(case: Case, profile: dict, manifest: dict) -> None:
    """Flywheel: arquiva a anotação humana de lesão para treino futuro.

    Cada lesão marcada à mão vira um dado rotulado. Acumulando, constrói-se o
    conjunto de treino que hoje não existe (contexto/06_SEGMENTACAO.md). Só dados
    anonimizados são arquivados.
    """
    base = (
        Path(profile.get("flywheel", {}).get("dir", "flywheel"))
        / profile["id"]
        / manifest["case_id"]
    )
    base.mkdir(parents=True, exist_ok=True)
    shutil.copy2(case.volume, base / "volume.nii.gz")
    shutil.copy2(case.mask_lesion, base / "mask_lesion.nii.gz")
    if case.mask_organ.exists():
        shutil.copy2(case.mask_organ, base / "mask_organ.nii.gz")
    (base / "meta.json").write_text(
        json.dumps(
            {
                "case_id": manifest["case_id"],
                "organ": profile["id"],
                "modality": manifest.get("modality"),
                "policy": manifest.get("policy"),
                "note": "Anotação humana de lesão p/ treino futuro (flywheel). "
                "Apenas dados anonimizados.",
                "created_utc": now_utc(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info("Flywheel: caso arquivado para treino futuro em %s", base)


def _refine_mask(mask_zyx, opening: bool, radius: int, min_voxels: int) -> np.ndarray:
    m = mask_zyx.astype(bool)
    fp = np.ones((int(radius),) * 3, dtype=bool)
    if opening:
        m = morphology.binary_opening(m, footprint=fp)  # API atual: footprint (não selem)
    m = morphology.binary_closing(m, footprint=fp)
    if min_voxels and int(min_voxels) > 0:
        m = morphology.remove_small_objects(m, min_size=int(min_voxels))
    return m.astype(np.uint8)


def _fonte_da_malha_do_orgao(case: Case) -> Path:
    """Fonte da máscara do órgão para VISUALIZAÇÃO (a malha 3D), não para
    classificação -- que nunca chama esta função e sempre lê case.mask_organ
    diretamente, antes de qualquer coisa aqui existir.

    Prefere a união de fases (docs/188 §9, docs/189) quando o webapp já a
    escreveu: validado contra referência humana que ela recupera fígado real
    (82% de precisão no que acrescenta) e mede 23% de volume a mais que a
    venosa sozinha na mediana, nas três fases de produção
    (experiments/three_phase_union_v1). Cai para a venosa quando a união não
    existe -- por exemplo no benchmark em lote, que não a constrói.
    """
    shadow = approved_visualization_mask(case.root)
    if shadow is not None:
        return shadow
    return case.mask_organ_union if case.mask_organ_union.is_file() else case.mask_organ


FRACAO_MINIMA_COMPONENTE_ORGAO = 0.90


def _isolar_orgao_para_visualizacao(
    mask_zyx, fracao_minima: float = FRACAO_MINIMA_COMPONENTE_ORGAO
) -> tuple[np.ndarray, dict]:
    """Deixa só o corpo principal do órgão, quando isso for seguro.

    Motivo (docs/188): o refino remove apenas objetos menores que 300 voxels
    (0,55 mL), então ilhas maiores sobrevivem e aparecem flutuando ao lado do
    fígado no visualizador. Medido em 30 casos, isolar o componente principal
    levou de 0% a 100% de corpo único nas malhas em que havia o que isolar, com
    custo mediano de volume de 0,0% -- as ilhas quase sempre são detritos.

    A GUARDA é o ponto central. Quando o componente principal não domina a
    máscara, o órgão não está "com ilhas": está partido em pedaços grandes, e
    isolar apagaria anatomia de verdade -- num caso da coorte, 47%. Nesse regime
    a fragmentação é sintoma de segmentação ruim, e esconder seria pior que
    mostrar. Então devolve-se a máscara intacta e o diagnóstico registra por quê.

    Aplica-se SOMENTE ao órgão. Lesões múltiplas e árvores vasculares são
    legitimamente multi-componente; isolar o maior ali apagaria achado real.
    """
    mask = np.asarray(mask_zyx).astype(bool)
    rotulos, n_componentes = ndimage.label(mask)

    if n_componentes <= 1:
        fracao, isolado, motivo = 1.0, False, "componente_unico_nada_a_isolar"
        corpo = mask
    else:
        tamanhos = np.bincount(rotulos.ravel())[1:]
        fracao = float(tamanhos.max() / tamanhos.sum())
        if fracao < float(fracao_minima):
            isolado, motivo = False, "orgao_partido_isolar_apagaria_anatomia"
            corpo = mask
        else:
            isolado, motivo = True, "componente_principal_domina"
            corpo = rotulos == (int(np.argmax(tamanhos)) + 1)

    # Cavidades internas viram transparências na malha e são preenchidas SEMPRE,
    # inclusive quando não houve isolamento -- uma máscara de componente único
    # também pode ter buraco dentro. É feito por último para que, no caso
    # partido, o preenchimento não funda os pedaços num só e desfaça a guarda.
    antes = int(corpo.sum())
    corpo = ndimage.binary_fill_holes(corpo)
    return corpo.astype(np.uint8), {
        "componentes": int(n_componentes),
        "fracao_componente_principal": round(float(fracao), 4),
        "isolado": bool(isolado),
        "motivo": motivo,
        "voxels_de_cavidade_preenchidos": int(corpo.sum()) - antes,
    }


def _campo_continuo(img, isotropic_mm: float, sigma_mm: float):
    """Máscara binária -> campo de distância isotrópico e suavizado.

    O marching cubes direto na grade de aquisição produz terraços porque a grade
    é fortemente anisotrópica -- exames de RM hepática chegam com 3 a 4x mais
    espaçamento em Z, e um fígado inteiro pode caber em 23 cortes. Os degraus são
    artefato de amostragem, não anatomia.

    A correção é marchar num campo CONTÍNUO: a distância com sinal carrega a
    posição sub-voxel da borda, então reamostrá-la interpola a forma em vez de
    replicar voxels. A gaussiana leve remove o que resta da escada.
    """
    dist = sitk.SignedMaurerDistanceMap(
        sitk.Cast(img, sitk.sitkUInt8),
        insideIsPositive=False,
        squaredDistance=False,
        useImageSpacing=True,
    )
    espac = np.array(dist.GetSpacing())
    tam = np.array(dist.GetSize())
    reamostra = sitk.ResampleImageFilter()
    reamostra.SetOutputSpacing([float(isotropic_mm)] * 3)
    reamostra.SetSize(np.ceil(tam * espac / float(isotropic_mm)).astype(int).tolist())
    reamostra.SetOutputOrigin(dist.GetOrigin())
    reamostra.SetOutputDirection(dist.GetDirection())
    reamostra.SetInterpolator(sitk.sitkLinear)
    reamostra.SetDefaultPixelValue(float(sitk.GetArrayViewFromImage(dist).max()))
    campo = reamostra.Execute(dist)
    if sigma_mm and float(sigma_mm) > 0:
        campo = sitk.SmoothingRecursiveGaussian(campo, sigma=float(sigma_mm))
    return campo


def _malha_do_campo(campo, nivel: float):
    arr = sitk.GetArrayFromImage(campo).astype(np.float32)
    if arr.min() > nivel or arr.max() < nivel:
        return None
    verts_zyx, faces, _n, _v = measure.marching_cubes(arr, level=nivel)
    verts_lps = world_vertices_from_index(verts_zyx, campo)
    faces_pv = np.hstack(
        [np.full((faces.shape[0], 1), 3, dtype=np.int64), faces]
    ).ravel()
    return pv.PolyData(verts_lps, faces_pv)


def _nivel_por_volume(campo, volume_alvo_ml: float, iteracoes: int = 7):
    """Escolhe o isovalor que faz a malha encerrar o volume MEDIDO na máscara.

    A gaussiana erode a superfície de forma sistemática: marchar em zero perde
    9 a 16% do volume, o que é infidelidade, não suavização. Em vez de aceitar
    essa perda ou de fixar um deslocamento arbitrário, busca-se por bisseção o
    nível que reproduz o volume da máscara. O critério é de fidelidade -- a
    superfície fica tão lisa quanto a suavização permite, mas obrigada a encerrar
    exatamente o volume que foi medido.
    """
    baixo, alto = 0.0, 3.0
    melhor, melhor_erro = None, float("inf")
    for _ in range(int(iteracoes)):
        meio = (baixo + alto) / 2.0
        m = _malha_do_campo(campo, meio)
        if m is None:
            alto = meio
            continue
        volume = float(m.volume) / 1000.0
        erro = abs(volume - volume_alvo_ml)
        if erro < melhor_erro:
            melhor, melhor_erro = (m, meio), erro
        if volume < volume_alvo_ml:
            baixo = meio
        else:
            alto = meio
    return melhor


def _mesh_from_mask(
    mask_path: Path,
    level: float,
    smooth_iter: int,
    feature_angle: float,
    pass_band: float = 0.1,
    isotropic_mm: float | None = None,
    gaussian_sigma_mm: float = 1.0,
    max_triangles: int = 0,
):
    img = read_image(mask_path)
    mask = array_from(img).astype(np.float32)
    if mask.max() < 0.5:
        return None  # máscara vazia
    if isotropic_mm and float(isotropic_mm) > 0:
        alvo_ml = float((mask > 0.5).sum()) * float(np.prod(img.GetSpacing())) / 1000.0
        # A busca do isovalor roda numa grade GROSSEIRA e a malha final numa fina:
        # o nível é uma distância em mm, então transfere entre resoluções. Sem
        # isso seriam sete marching cubes na grade fina -- 8 s por estrutura, o
        # que triplicaria o tempo do exame com uma dúzia de estruturas.
        grosso = _campo_continuo(img, float(isotropic_mm) * 2.0, gaussian_sigma_mm)
        escolha = _nivel_por_volume(grosso, alvo_ml)
        if escolha is None:
            return None
        _, nivel = escolha
        campo = _campo_continuo(img, float(isotropic_mm), gaussian_sigma_mm)
        mesh = _malha_do_campo(campo, nivel)
        if mesh is None:
            return None
        if max_triangles and mesh.n_cells > int(max_triangles):
            # Decimação quadrática: preserva a forma muito melhor que subamostrar,
            # e mantém o STL num tamanho que o navegador carrega sem engasgar.
            mesh = mesh.decimate(1.0 - float(max_triangles) / mesh.n_cells)
        if smooth_iter and int(smooth_iter) > 0:
            mesh = mesh.smooth_taubin(
                n_iter=int(smooth_iter),
                pass_band=float(pass_band),
                feature_angle=float(feature_angle),
            )
        log.info(
            "Malha de %s: campo contínuo %.2f mm, sigma %.2f, nível %.3f mm, "
            "volume %.0f mL (alvo %.0f mL), %d triângulos.",
            mask_path.name, float(isotropic_mm), float(gaussian_sigma_mm),
            nivel, mesh.volume / 1000.0, alvo_ml, mesh.n_cells,
        )
        return mesh
    try:
        verts_zyx, faces, _n, _v = measure.marching_cubes(mask, level=level)
    except (ValueError, RuntimeError) as e:
        raise PipelineError(
            f"Falha no marching cubes de {mask_path.name}: {e}"
        ) from e
    # Vértices em coordenadas físicas LPS (origin+direction+spacing da própria máscara).
    verts_lps = world_vertices_from_index(verts_zyx, img)
    # PyVista exige o contador de vértices por face: [3, i, j, k, 3, i, j, k, ...].
    # (Corrige o reshape(-1,3) do original, que embaralhava as faces.)
    faces_pv = np.hstack(
        [np.full((faces.shape[0], 1), 3, dtype=np.int64), faces]
    ).ravel()
    mesh = pv.PolyData(verts_lps, faces_pv)
    if smooth_iter and int(smooth_iter) > 0:
        # Taubin (windowed-sinc) em vez do Laplaciano: remove a "escada" de
        # voxels do marching cubes PRESERVANDO o volume. O Laplaciano encolhe a
        # malha a cada iteração, deixando o fígado como uma bolha menor e menos
        # fiel; o Taubin mantém as dimensões reais do órgão enquanto arredonda.
        mesh = mesh.smooth_taubin(
            n_iter=int(smooth_iter),
            pass_band=float(pass_band),
            feature_angle=float(feature_angle),
        )
    return mesh


# --------------------------------------------------------------------------- #
# (1) Ingestão + des-identificação
# --------------------------------------------------------------------------- #
def stage1_ingest(case: Case, profile: dict, dicom_dir, policy: str) -> None:
    dicom_dir = Path(dicom_dir)
    if not dicom_dir.is_dir():
        raise PipelineError(f"Pasta DICOM inexistente: {dicom_dir}")

    first = _first_dicom(dicom_dir)
    if first is None:
        raise PipelineError(f"Nenhum arquivo DICOM legível em {dicom_dir}")

    ds = pydicom.dcmread(first, stop_before_pixels=True, force=True)
    modality = str(getattr(ds, "Modality", "") or "").upper()
    expected = [str(m).upper() for m in profile["modalidade"]]
    if modality and modality not in expected:
        raise PipelineError(
            f"Modalidade do exame ({modality}) não bate com o perfil "
            f"'{profile['id']}' (espera {expected}). Use o perfil correto."
        )

    image = read_dicom_series(dicom_dir)
    if image.GetSize()[2] < MIN_SLICES:
        raise PipelineError(
            f"Série com poucas fatias ({image.GetSize()[2]}); volume 3D inviável."
        )

    case.root.mkdir(parents=True, exist_ok=True)
    # Anonimização (MVP): converter para NIfTI descarta os cabeçalhos DICOM, então
    # nenhum identificador (nome, ID, datas) viaja adiante.
    save_image(image, case.volume)

    case_id = _make_case_id(policy, ds)
    manifest = {
        "case_id": case_id,
        "policy": policy,
        "modality": modality or "DESCONHECIDA",
        "size_xyz": list(image.GetSize()),
        "spacing_xyz": [float(x) for x in image.GetSpacing()],
        "origin_xyz": [float(x) for x in image.GetOrigin()],
        "volume_sha256": sha256_of(case.volume),
        "regulatory_state": profile.get("estado_regulatorio", "PESQUISA"),
        "software": "digital-twin-pipeline (MVP, Nível 1, modo Pesquisa)",
        "created_utc": now_utc(),
        "caveats": [
            "PHI gravada nos pixels (burned-in) NÃO é detectada automaticamente; "
            "exige verificação humana.",
        ],
    }
    case.write_manifest(manifest)
    log.info(
        "Estágio 1: volume %s, spacing %s mm, case_id=%s, modo=%s.",
        tuple(image.GetSize()),
        tuple(round(s, 3) for s in image.GetSpacing()),
        case_id,
        policy,
    )


# --------------------------------------------------------------------------- #
# (2) Normalização (referência/inspeção; NÃO é o que vai para o segmentador)
# --------------------------------------------------------------------------- #
def stage2_normalize(case: Case, profile: dict) -> None:
    img = read_image(case.volume)
    arr = array_from(img).astype(np.float32)
    method = str(profile.get("normalizacao", "zscore")).lower()

    if method == "zscore":
        std = float(arr.std())
        if std < 1e-6:
            raise PipelineError(
                "Volume praticamente constante (std~0); exame possivelmente corrompido."
            )
        norm = (arr - float(arr.mean())) / (std + 1e-8)
    elif method == "minmax":
        lo, hi = float(arr.min()), float(arr.max())
        if hi - lo < 1e-6:
            raise PipelineError(
                "Volume sem contraste (min==max); exame possivelmente corrompido."
            )
        norm = (arr - lo) / (hi - lo)
    else:
        raise PipelineError(
            f"Normalização '{method}' não suportada (use zscore ou minmax)."
        )

    save_image(array_to_image(norm, img, np.float32), case.volume_zscore)
    # NOTA: este volume normalizado é só referência. O estágio 3 alimenta o
    # TotalSegmentator com o volume ORIGINAL (case.volume); o modelo faz a própria
    # normalização interna. Não duplicar (contexto/05_PIPELINE.md).
    log.info("Estágio 2: volume normalizado (%s) salvo para referência.", method)


def _anatomy_structures(profile: dict) -> list[tuple[str, dict]]:
    """Lê estruturas internas opcionais do perfil de modo estritamente local.

    O perfil, e não o DICOM ou o navegador, define os rótulos e os papéis que
    podem ser exportados. Assim nenhuma estrutura inesperada é publicada.
    """
    config = profile.get("segmentacao_anatomia") or {}
    if not config.get("habilitada", False):
        return []
    tasks = config.get("tarefas")
    if not isinstance(tasks, list):
        raise PipelineError("segmentacao_anatomia.tarefas deve ser uma lista.")
    structures: list[tuple[str, dict]] = []
    roles: set[str] = set()
    for task_entry in tasks:
        if not isinstance(task_entry, dict):
            raise PipelineError("Cada tarefa anatômica deve ser um objeto.")
        task = str(task_entry.get("motor_task") or "").strip()
        entries = task_entry.get("estruturas")
        if not task or not isinstance(entries, list):
            raise PipelineError("Tarefa anatômica exige motor_task e estruturas.")
        for entry in entries:
            if not isinstance(entry, dict):
                raise PipelineError("Cada estrutura anatômica deve ser um objeto.")
            role = str(entry.get("papel") or "").strip()
            label = str(entry.get("rotulo") or "").strip()
            if (
                not role
                or not label
                or not role.replace("_", "").isalnum()
                or role in roles
            ):
                raise PipelineError("Estrutura anatômica possui papel/rótulo inválido ou duplicado.")
            roles.add(role)
            structures.append((task, dict(entry)))
    return structures


def _remove_anatomy_artifacts(case: Case, role: str) -> None:
    """Remove somente artefatos derivados de uma estrutura opcional ausente."""
    for path in (
        case.anatomy_mask(role),
        case.anatomy_mask(role, clean=True),
        case.anatomy_mesh(role),
    ):
        if path.exists():
            path.unlink()


# --------------------------------------------------------------------------- #
# (3) Segmentação do ÓRGÃO — automática (TotalSegmentator MRI). GATE CRÍTICO.
# --------------------------------------------------------------------------- #
def stage3_segment_organ(case: Case, profile: dict, device: str, fast: bool) -> None:
    seg = profile["segmentacao_orgao"]
    task = seg.get("motor_task", "total_mr")
    label = seg["rotulo_alvo"]
    anatomy = _anatomy_structures(profile)
    anatomy_fast_by_task: dict[str, bool] = {}
    anatomy_require_complete: dict[str, bool] = {}
    for task_entry in (profile.get("segmentacao_anatomia") or {}).get("tarefas", []):
        current_task = str(task_entry.get("motor_task") or "").strip()
        configured_fast = task_entry.get("fast", fast)
        if not isinstance(configured_fast, bool):
            raise PipelineError(
                f"segmentacao_anatomia.tarefas[{current_task}].fast deve ser booleano."
            )
        anatomy_fast_by_task[current_task] = configured_fast
        require_complete = task_entry.get("require_complete", False)
        if not isinstance(require_complete, bool):
            raise PipelineError(
                f"segmentacao_anatomia.tarefas[{current_task}].require_complete deve ser booleano."
            )
        anatomy_require_complete[current_task] = require_complete

    try:
        from totalsegmentator.python_api import totalsegmentator
    except ImportError as e:
        raise PipelineError(
            "TotalSegmentator não está instalado. O pipeline ABORTA (regra de ouro "
            "nº 1): jamais gerar máscara aleatória, como o script original fazia. "
            "Instale com: pip install TotalSegmentator"
        ) from e

    case.seg_dir.mkdir(parents=True, exist_ok=True)
    labels_by_task: dict[str, set[str]] = {str(task): {str(label)}}
    for anatomy_task, entry in anatomy:
        labels_by_task.setdefault(anatomy_task, set()).add(str(entry["rotulo"]))
    for current_task, labels in labels_by_task.items():
        try:
            call_kwargs = {
                "input": str(case.volume),
                "output": str(case.seg_dir),
                "task": current_task,
                "device": device,
                "fast": (
                    fast
                    if current_task == task
                    else anatomy_fast_by_task.get(current_task, fast)
                ),
                "quiet": True,
            }
            # A API do TotalSegmentator 2.x aceita roi_subset apenas nas tasks
            # gerais. Tasks dedicadas (como liver_segments_mr) já têm um
            # conjunto fechado de classes e abortam se esse argumento chegar.
            if current_task in {"total", "total_mr"}:
                call_kwargs["roi_subset"] = sorted(labels)
            totalsegmentator(
                **call_kwargs,
            )
        except Exception as e:  # noqa: BLE001
            if current_task == task:
                raise PipelineError(
                    f"Falha na segmentação automática ({task}/{label}): {e}"
                ) from e
            # Anatomia interna é complementar ao fígado principal; sua falha
            # não cria dado sintético nem invalida um caso já segmentado.
            log.warning("Anatomia interna não disponível (%s): %s", current_task, e)

    produced = case.seg_dir / f"{label}.nii.gz"
    if not produced.exists():
        raise PipelineError(
            f"Saída de segmentação esperada não encontrada: {produced}. "
            f"Verifique se '{label}' é classe válida da task '{task}' "
            f"(rode: totalseg_info --classes -ta {task})."
        )

    organ_img = read_image(produced)
    if int(array_from(organ_img).sum()) == 0:
        raise PipelineError(
            f"Segmentação automática não encontrou '{label}' no exame. "
            "Revisão humana necessária (não há órgão a modelar)."
        )

    save_image(organ_img, case.mask_organ)
    log.info("Estágio 3: órgão '%s' segmentado automaticamente (task=%s).", label, task)

    volume_geometry = read_image(case.volume)
    anatomy_validity: dict[tuple[str, str], bool] = {}
    for anatomy_task, entry in anatomy:
        role = str(entry["papel"])
        produced = case.seg_dir / f"{entry['rotulo']}.nii.gz"
        valid = False
        if produced.exists():
            produced_image = read_image(produced)
            valid = bool(
                int(array_from(produced_image).sum()) > 0
                and produced_image.GetSize() == volume_geometry.GetSize()
                and np.allclose(produced_image.GetSpacing(), volume_geometry.GetSpacing(), atol=1e-6)
                and np.allclose(produced_image.GetOrigin(), volume_geometry.GetOrigin(), atol=1e-5)
                and np.allclose(produced_image.GetDirection(), volume_geometry.GetDirection(), atol=1e-6)
            )
        anatomy_validity[(anatomy_task, role)] = valid

    incomplete_tasks = {
        anatomy_task
        for anatomy_task, _ in anatomy
        if anatomy_require_complete.get(anatomy_task, False)
        and not all(
            anatomy_validity[(task_name, str(task_entry["papel"]))]
            for task_name, task_entry in anatomy
            if task_name == anatomy_task
        )
    }

    for anatomy_task, entry in anatomy:
        role = str(entry["papel"])
        produced = case.seg_dir / f"{entry['rotulo']}.nii.gz"
        if anatomy_task in incomplete_tasks or not anatomy_validity[(anatomy_task, role)]:
            _remove_anatomy_artifacts(case, role)
            log.info("Estágio 3: anatomia opcional ausente (%s/%s).", anatomy_task, role)
            continue
        shutil.copyfile(produced, case.anatomy_mask(role))
        log.info("Estágio 3: anatomia interna '%s' disponível (%s).", role, anatomy_task)


# --------------------------------------------------------------------------- #
# (4a) Preparar marcação da LESÃO — handoff para o 3D Slicer
# --------------------------------------------------------------------------- #
def stage4a_prepare_lesion(case: Case, profile: dict) -> None:
    if not case.volume.exists() or not case.mask_organ.exists():
        raise PipelineError("Estágios 1–3 incompletos; rode 'prepare' do início.")

    tools = ", ".join(
        profile.get("segmentacao_lesao", {}).get(
            "ferramentas_sugeridas", ["threshold", "region_growing", "paint"]
        )
    )
    msg = textwrap.dedent(
        f"""
    ------------------------------------------------------------------
    REVISÃO HUMANA NECESSÁRIA — 3D Slicer (estágio 4)
    A segmentação do órgão é automática; a LESÃO é marcada por humano.

      1) Abra o 3D Slicer e carregue:
           Volume : {case.volume}
           Órgão  : {case.mask_organ}   (revise e corrija se necessário)
      2) Crie um novo segmento para a LESÃO usando: {tools}.
      3) Salve a máscara da lesão EXATAMENTE em:
           {case.mask_lesion}
      4) (Opcional) Se corrigiu o órgão, sobrescreva:
           {case.mask_organ}

    Depois finalize com:
       python digital_twin.py finalize "{case.root}" --profile <perfil>
    Se o caso REALMENTE não tiver lesão, finalize com --no-lesion.
    ------------------------------------------------------------------
    """
    )
    print(msg)
    log.info("Estágio 4a: aguardando marcação da lesão no 3D Slicer.")


# --------------------------------------------------------------------------- #
# (4b) Importar LESÃO marcada + arquivar para o flywheel
# --------------------------------------------------------------------------- #
def stage4b_import_lesion(case: Case, profile: dict, no_lesion: bool) -> None:
    if not case.mask_organ.exists():
        raise PipelineError(
            "Máscara do órgão ausente; rode 'prepare' antes de 'finalize'."
        )

    if not case.mask_lesion.exists():
        if no_lesion:
            ref = read_image(case.mask_organ)
            empty = array_to_image(
                np.zeros(array_from(ref).shape, dtype=np.uint8), ref, np.uint8
            )
            save_image(empty, case.mask_lesion)
            log.warning(
                "Estágio 4b: caso sem lesão por escolha explícita (--no-lesion)."
            )
        else:
            raise PipelineError(
                f"Máscara de lesão ausente: {case.mask_lesion}\n"
                "Marque a lesão no 3D Slicer (ver instruções do 'prepare') e salve "
                "nesse caminho, ou rode 'finalize' com --no-lesion se não houver lesão."
            )

    lesion = read_image(case.mask_lesion)
    organ = read_image(case.mask_organ)
    if lesion.GetSize() != organ.GetSize():
        raise PipelineError(
            "Máscara de lesão com tamanho diferente do volume/órgão "
            f"({lesion.GetSize()} != {organ.GetSize()}). Refaça a marcação sobre o "
            "volume correto no Slicer."
        )

    l = array_from(lesion).astype(bool)
    o = array_from(organ).astype(bool)
    if l.sum() > 0 and not (l & o).any():
        # Aviso (não-gate): lesão adjacente pode ser legítima, mas costuma indicar erro.
        log.warning("Estágio 4b: a lesão marcada não sobrepõe o órgão. Confira no Slicer.")

    manifest = case.read_manifest()
    if manifest.get("policy") == "anonymize" and l.sum() > 0:
        _archive_for_training(case, profile, manifest)
    log.info("Estágio 4b: lesão importada e validada.")


# --------------------------------------------------------------------------- #
# (5) Refino das máscaras
# --------------------------------------------------------------------------- #
def stage5_refine(case: Case, profile: dict) -> None:
    refino = profile.get("refino", {})

    # Órgão -- a fonte é a VISUALIZAÇÃO (união de fases se disponível), nunca a
    # classificação, que já rodou sobre case.mask_organ antes deste estágio.
    organ_source = _fonte_da_malha_do_orgao(case)
    if organ_source != case.mask_organ:
        # Defesa contra um arquivo de união corrompido/deslocado: se a
        # geometria não bate com a venosa (a referência garantida), volta para
        # ela em vez de deformar a malha silenciosamente.
        referencia = read_image(case.mask_organ)
        candidata = read_image(organ_source)
        if (
            candidata.GetSize() != referencia.GetSize()
            or candidata.GetSpacing() != referencia.GetSpacing()
            or candidata.GetOrigin() != referencia.GetOrigin()
        ):
            log.warning(
                "Estágio 5: %s tem geometria divergente da venosa; "
                "descartando e usando a venosa.", organ_source.name,
            )
            organ_source = case.mask_organ
    organ_img = read_image(organ_source)
    organ = array_from(organ_img)
    oc = refino.get("orgao", {})
    organ_clean = _refine_mask(
        organ, oc.get("opening", True), oc.get("opening_radius", 2),
        oc.get("min_volume_voxels", 300),
    )
    if organ.sum() > 0 and organ_clean.sum() == 0:
        raise PipelineError(
            "Refino zerou a máscara do órgão — parâmetros mal calibrados (refino.orgao)."
        )
    antes_isolar = int(organ_clean.sum())
    organ_clean, diagnostico_componentes = _isolar_orgao_para_visualizacao(
        organ_clean, float(oc.get("fracao_minima_componente", FRACAO_MINIMA_COMPONENTE_ORGAO))
    )
    if organ_clean.sum() == 0:
        raise PipelineError("Isolamento do órgão zerou a máscara.")
    save_image(array_to_image(organ_clean, organ_img, np.uint8), case.mask_organ_clean)
    log.info(
        "Estágio 5: órgão refinado a partir de %s (%d -> %d voxels); "
        "componentes %d, fração do principal %.4f, isolado=%s (%s).",
        organ_source.name, int(organ.sum()), int(organ_clean.sum()),
        diagnostico_componentes["componentes"],
        diagnostico_componentes["fracao_componente_principal"],
        diagnostico_componentes["isolado"], diagnostico_componentes["motivo"],
    )
    if diagnostico_componentes["isolado"]:
        log.info(
            "Estágio 5: %d voxels de fragmento removidos da visualização.",
            antes_isolar - int(organ_clean.sum()),
        )

    # Região classificada -- só existe quando a malha do órgão veio da união
    # (docs/188 §9, docs/189 §5.2): sem união, ela seria idêntica ao órgão
    # inteiro, um overlay sobre si mesmo, ruído puro. Mesmo refino/isolamento
    # da venosa crua (case.mask_organ), para ficar geometricamente comparável
    # ao órgão que o estágio 7 vai publicar ao lado dela.
    if organ_source != case.mask_organ:
        venosa_img = read_image(case.mask_organ)
        venosa = array_from(venosa_img)
        classificada_clean = _refine_mask(
            venosa, oc.get("opening", True), oc.get("opening_radius", 2),
            oc.get("min_volume_voxels", 300),
        )
        classificada_clean, diagnostico_classificada = _isolar_orgao_para_visualizacao(
            classificada_clean,
            float(oc.get("fracao_minima_componente", FRACAO_MINIMA_COMPONENTE_ORGAO)),
        )
        if classificada_clean.sum() > 0:
            save_image(
                array_to_image(classificada_clean, venosa_img, np.uint8),
                case.mask_organ_classified_region_clean,
            )
            log.info(
                "Estágio 5: região classificada (venosa) publicada como overlay "
                "(%d voxels; fração do fígado exibido: %.3f).",
                int(classificada_clean.sum()),
                float(classificada_clean.sum()) / float(max(organ_clean.sum(), 1)),
            )
        else:
            case.mask_organ_classified_region_clean.unlink(missing_ok=True)
    else:
        # Sem união nesta execução: remove overlay de uma execução anterior
        # para não publicar um dado fantasma (finalize precisa ser idempotente).
        case.mask_organ_classified_region_clean.unlink(missing_ok=True)

    # Lesão (gentil: não apagar lesões pequenas)
    lesion_img = read_image(case.mask_lesion)
    lesion = array_from(lesion_img)
    if lesion.sum() == 0:
        save_image(array_to_image(lesion, lesion_img, np.uint8), case.mask_lesion_clean)
        log.info("Estágio 5: sem lesão a refinar.")
    else:
        lc = refino.get("lesao", {})
        lesion_clean = _refine_mask(
            lesion, lc.get("opening", False), lc.get("opening_radius", 1),
            lc.get("min_volume_voxels", 30),
        )
        if lesion_clean.sum() == 0:
            raise PipelineError(
                "Refino zerou a máscara da lesão — afrouxe refino.lesao "
                "(a lesão pode ser pequena)."
            )
        save_image(array_to_image(lesion_clean, lesion_img, np.uint8), case.mask_lesion_clean)
        log.info(
            "Estágio 5: lesão refinada (%d -> %d voxels).",
            int(lesion.sum()), int(lesion_clean.sum()),
        )

    # Anatomia interna é complementar: não pode apagar a máscara hepática nem
    # bloquear a revisão quando um modelo auxiliar não encontra uma estrutura.
    ac = refino.get("anatomia", {})
    for _, entry in _anatomy_structures(profile):
        role = str(entry["papel"])
        raw_path = case.anatomy_mask(role)
        clean_path = case.anatomy_mask(role, clean=True)
        if not raw_path.exists():
            if clean_path.exists():
                clean_path.unlink()
            continue
        anatomy_img = read_image(raw_path)
        anatomy = array_from(anatomy_img)
        anatomy_clean = _refine_mask(
            anatomy,
            ac.get("opening", False),
            ac.get("opening_radius", 1),
            ac.get("min_volume_voxels", 20),
        )
        if anatomy.sum() > 0 and anatomy_clean.sum() == 0:
            log.warning("Estágio 5: anatomia '%s' removida pelo refino; omitindo-a.", role)
            if clean_path.exists():
                clean_path.unlink()
            continue
        save_image(array_to_image(anatomy_clean, anatomy_img, np.uint8), clean_path)
        log.info(
            "Estágio 5: anatomia '%s' refinada (%d -> %d voxels).",
            role, int(anatomy.sum()), int(anatomy_clean.sum()),
        )

    # Região candidata automática, gerada SOMENTE depois da inferência. Ela é
    # mantida separada da lesão manual e nunca alimenta o classificador.
    if not case.mask_candidate.exists():
        case.mask_candidate_clean.unlink(missing_ok=True)
    else:
        if not case.candidate_manifest.is_file():
            raise PipelineError("Região candidata sem manifesto de proveniência.")
        try:
            candidate_receipt = json.loads(case.candidate_manifest.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("Manifesto da região candidata inválido.") from exc
        if (
            candidate_receipt.get("schema") != "argos-candidate-region-v1"
            or candidate_receipt.get("used_by_screening_inference") is not False
            or candidate_receipt.get("candidate_is_diagnosis") is not False
            or candidate_receipt.get("mask_sha256") != sha256_of(case.mask_candidate)
        ):
            raise PipelineError("Integridade/proveniência da região candidata falhou.")
        candidate_image = read_image(case.mask_candidate)
        if (
            candidate_image.GetSize() != organ_img.GetSize()
            or not np.allclose(candidate_image.GetSpacing(), organ_img.GetSpacing(), atol=1e-6)
            or not np.allclose(candidate_image.GetOrigin(), organ_img.GetOrigin(), atol=1e-5)
            or not np.allclose(candidate_image.GetDirection(), organ_img.GetDirection(), atol=1e-6)
        ):
            raise PipelineError("Região candidata diverge da geometria hepática.")
        candidate = array_from(candidate_image)
        if not np.isfinite(candidate).all() or not np.isin(np.unique(candidate), [0, 1]).all():
            raise PipelineError("Região candidata não é binária.")
        cc = refino.get("candidato", {})
        candidate_clean = _refine_mask(
            candidate,
            cc.get("opening", False),
            cc.get("opening_radius", 1),
            cc.get("min_volume_voxels", 1),
        )
        save_image(
            array_to_image(candidate_clean, candidate_image, np.uint8),
            case.mask_candidate_clean,
        )
        log.info(
            "Estágio 5: região candidata automática preservada (%d -> %d voxels).",
            int(candidate.sum()), int(candidate_clean.sum()),
        )


# --------------------------------------------------------------------------- #
# (6) Geração de malha (superfície). FEA/tetraedralização = fase 2.
# --------------------------------------------------------------------------- #
def stage6_mesh(case: Case, profile: dict) -> None:
    mesh_cfg = profile.get("mesh", {})
    level = float(mesh_cfg.get("nivel_marching_cubes", 0.5))
    sm = int(mesh_cfg.get("suavizacao_iteracoes", 30))
    fa = float(mesh_cfg.get("feature_angle", 60.0))
    pb = float(mesh_cfg.get("taubin_pass_band", 0.1))
    # Reconstrução por campo contínuo: 0 ou ausente mantém o caminho antigo.
    iso = float(mesh_cfg.get("reamostragem_isotropica_mm", 0.0) or 0.0)
    sigma = float(mesh_cfg.get("suavizacao_campo_sigma_mm", 1.0))
    maxtri = int(mesh_cfg.get("max_triangulos", 0) or 0)
    extra = {"isotropic_mm": iso, "gaussian_sigma_mm": sigma, "max_triangles": maxtri}

    organ_mesh = _mesh_from_mask(case.mask_organ_clean, level, sm, fa, pass_band=pb, **extra)
    if organ_mesh is None:
        raise PipelineError(
            "Malha do órgão vazia — máscara do órgão sem conteúdo após refino."
        )
    organ_mesh.save(str(case.mesh_organ))
    log.info(
        "Estágio 6: malha do órgão (%d vértices, %d faces).",
        organ_mesh.n_points, organ_mesh.n_cells,
    )

    lesion_mesh = _mesh_from_mask(case.mask_lesion_clean, level, sm, fa, pass_band=pb, **extra)
    if lesion_mesh is not None:
        lesion_mesh.save(str(case.mesh_lesion))
        log.info(
            "Estágio 6: malha da lesão (%d vértices, %d faces).",
            lesion_mesh.n_points, lesion_mesh.n_cells,
        )
    else:
        # Sem lesão: remove malha de uma execução anterior para que o estágio 7 não
        # republique uma lesão obsoleta (finalize idempotente, sem dado fantasma).
        if case.mesh_lesion.exists():
            case.mesh_lesion.unlink()
            log.info("Estágio 6: malha de lesão obsoleta removida (caso sem lesão).")
        log.info("Estágio 6: sem malha de lesão (máscara vazia).")

    candidate_mesh = (
        _mesh_from_mask(case.mask_candidate_clean, level, sm, fa, pass_band=pb, **extra)
        if case.mask_candidate_clean.is_file()
        else None
    )
    if candidate_mesh is not None:
        candidate_mesh.save(str(case.mesh_candidate))
        log.info(
            "Estágio 6: malha candidata não confirmada (%d vértices, %d faces).",
            candidate_mesh.n_points, candidate_mesh.n_cells,
        )
    else:
        case.mesh_candidate.unlink(missing_ok=True)

    classified_region_mesh = (
        _mesh_from_mask(case.mask_organ_classified_region_clean, level, sm, fa, pass_band=pb, **extra)
        if case.mask_organ_classified_region_clean.is_file()
        else None
    )
    if classified_region_mesh is not None:
        classified_region_mesh.save(str(case.mesh_organ_classified_region))
        log.info(
            "Estágio 6: malha da região classificada (%d vértices, %d faces).",
            classified_region_mesh.n_points, classified_region_mesh.n_cells,
        )
    else:
        case.mesh_organ_classified_region.unlink(missing_ok=True)

    for _, entry in _anatomy_structures(profile):
        role = str(entry["papel"])
        clean_path = case.anatomy_mask(role, clean=True)
        mesh_path = case.anatomy_mesh(role)
        if not clean_path.exists():
            if mesh_path.exists():
                mesh_path.unlink()
            continue
        anatomy_mesh = _mesh_from_mask(clean_path, level, sm, fa, pass_band=pb, **extra)
        if anatomy_mesh is None:
            if mesh_path.exists():
                mesh_path.unlink()
            continue
        anatomy_mesh.save(str(mesh_path))
        log.info(
            "Estágio 6: malha anatômica '%s' (%d vértices, %d faces).",
            role, anatomy_mesh.n_points, anatomy_mesh.n_cells,
        )


# --------------------------------------------------------------------------- #
# (7) Exportação STL (LPS) + publicação para o visualizador web
# --------------------------------------------------------------------------- #
def stage7_export_publish(case: Case, profile: dict) -> None:
    case.outputs.mkdir(parents=True, exist_ok=True)
    viewer_manifest_path = case.outputs / "viewer_manifest.json"
    # Um finalize interrompido não pode deixar o webapp republicar um manifesto
    # antigo como se descrevesse os novos artefatos.
    if viewer_manifest_path.exists():
        viewer_manifest_path.unlink()
    mesh_cfg = profile.get("mesh", {})
    viewer_cfg = profile.get("viewer", {}) or {}
    quality_cfg = viewer_cfg.get("quality_metrics", {}) or {}
    anatomy = _anatomy_structures(profile)
    couinaud_roles = [
        str(entry["papel"])
        for _, entry in anatomy
        if str(entry["papel"]).startswith("couinaud_")
    ]
    has_couinaud = bool(couinaud_roles) and all(
        case.anatomy_mesh(role).exists() for role in couinaud_roles
    )
    plan = [
        {
            "role": "orgao", "vtp": case.mesh_organ,
            "mask": case.mask_organ_clean,
            "color": mesh_cfg.get("cor_orgao", "#C8A27D"),
            # 0,5 deixava o parênquima com aparência de gelatina e escondia o
            # relevo da superfície -- justamente o que a malha nova passou a
            # descrever bem. 0,88 mantém os vasos visíveis por dentro sem
            # dissolver o órgão; o controle deslizante segue disponível.
            "label": "Fígado", "material": "organ", "opacity": 0.88,
            "default_visible": not has_couinaud,
        },
        {
            "role": "lesao", "vtp": case.mesh_lesion,
            "mask": case.mask_lesion_clean,
            "color": mesh_cfg.get("cor_lesao", "#D7263D"),
            "label": "Lesão marcada manualmente", "material": "lesion", "opacity": 1.0,
            "default_visible": True,
        },
        {
            "role": "candidato", "vtp": case.mesh_candidate,
            "mask": case.mask_candidate_clean,
            "color": mesh_cfg.get("cor_candidato", "#FF8400"),
            "label": "Região candidata automática — não confirmada",
            "material": "candidate", "opacity": 0.78,
            "default_visible": True,
        },
        {
            # Só existe quando o órgão vem da união de fases (docs/188 §9,
            # docs/189 §5.2): marca, dentro do modelo anatômico maior, qual
            # parte é a fase venosa que de fato alimentou a classificação. A
            # cor precisa contrastar com órgão (âmbar), lesão (vermelho) e
            # candidato (laranja) -- um ciano frio lê como "camada de
            # auditoria", não como tecido.
            "role": "regiao_classificada", "vtp": case.mesh_organ_classified_region,
            "mask": case.mask_organ_classified_region_clean,
            "color": mesh_cfg.get("cor_regiao_classificada", "#4FC3E8"),
            "label": "Região que alimentou a classificação (fase venosa)",
            "material": "classified_region", "opacity": 0.45,
            "default_visible": True,
        },
    ]
    for _, entry in anatomy:
        role = str(entry["papel"])
        plan.append({
            "role": role,
            "vtp": case.anatomy_mesh(role),
            "mask": case.anatomy_mask(role, clean=True),
            "color": str(entry.get("cor", "#C8A27D")),
            "label": str(entry.get("nome", role)),
            "material": str(entry.get("material", "anatomy")),
            "opacity": float(entry.get("opacidade", 0.8)),
            "default_visible": True,
        })

    items = []
    meshes_by_role: dict[str, pv.PolyData] = {}
    for spec in plan:
        role, vtp, color = spec["role"], spec["vtp"], spec["color"]
        stl = case.outputs / f"{profile['id']}_{role}.stl"
        if not vtp.exists():
            # Remove STL de execução anterior para este papel; sem isso, um caso
            # que deixou de ter lesão republicaria o STL antigo (dado fantasma).
            if stl.exists():
                stl.unlink()
                log.info("Estágio 7: STL obsoleto removido -> %s", stl)
            continue
        mesh = pv.read(str(vtp))
        try:
            mesh.save(str(stl))  # API correta (corrige o pv.save_mesh_as inexistente)
        except Exception as e:  # noqa: BLE001
            raise PipelineError(f"Falha ao exportar STL {stl}: {e}") from e
        metrics = compute_mesh_metrics(
            Path(spec["mask"]),
            mesh,
            stl,
            max_volume_error_percent=float(
                quality_cfg.get("max_volume_error_percent", 2.0)
            ),
            max_surface_p95_voxels=float(
                quality_cfg.get("max_surface_p95_voxels", 1.0)
            ),
        )
        xr_asset = build_xr_render_asset(
            mesh=mesh,
            source_stl=stl,
            source_metrics=metrics,
            mask_path=Path(spec["mask"]),
            output_path=case.outputs / f"{profile['id']}_{role}_xr_lod1.stl",
            material=str(spec["material"]),
            max_volume_error_percent=float(
                quality_cfg.get("max_volume_error_percent", 2.0)
            ),
            max_surface_p95_voxels=float(
                quality_cfg.get("max_surface_p95_voxels", 1.0)
            ),
        )
        meshes_by_role[role] = mesh
        items.append({
            "role": role,
            "stl": stl.name,
            "color": color,
            "label": spec["label"],
            "material": spec["material"],
            "opacity": spec["opacity"],
            "default_visible": spec["default_visible"],
            "metrics": metrics,
            "xr_asset": xr_asset,
        })
        log.info("Estágio 7: STL exportado -> %s", stl)

    if not items:
        raise PipelineError("Nenhuma malha para exportar.")

    manifest = case.read_manifest()
    reference_images = generate_reference_images(
        case.volume,
        case.mask_organ_clean,
        case.outputs,
        case.mask_candidate_clean if case.mask_candidate_clean.is_file() else None,
    )
    acquisition = acquisition_summary(
        case.volume,
        case.mask_organ_clean,
        mesh_isotropic_spacing_mm=float(mesh_cfg.get("reamostragem_isotropica_mm", 0.0)),
        mesh_smoothing_sigma_mm=float(mesh_cfg.get("suavizacao_campo_sigma_mm", 0.0)),
    )
    target_roles = [
        item["role"]
        for item in items
        if item["role"] == "orgao" or item.get("material") == "vessel"
    ]
    relationship_source = "lesao" if "lesao" in meshes_by_role else "candidato"
    relationships = nearest_surface_relationships(
        meshes_by_role, target_roles, source_role=relationship_source
    )
    segment_masks = {
        str(entry["papel"]): case.anatomy_mask(str(entry["papel"]), clean=True)
        for _, entry in anatomy
        if str(entry["papel"]).startswith("couinaud_")
        and case.anatomy_mask(str(entry["papel"]), clean=True).is_file()
    }
    lesion_context = lesion_segment_overlap(case.mask_lesion_clean, segment_masks)
    candidate_context = lesion_segment_overlap(case.mask_candidate_clean, segment_masks)
    if candidate_context:
        candidate_context["source"] = (
            "automatic_unconfirmed_candidate_mask_and_automatic_couinaud_masks"
        )
        candidate_context["candidate_voxels"] = candidate_context.pop("lesion_voxels")
        for overlap in candidate_context.get("overlaps", []):
            if "lesion_overlap_percent" in overlap:
                overlap["candidate_overlap_percent"] = overlap.pop(
                    "lesion_overlap_percent"
                )
    candidate_region = None
    if case.candidate_manifest.is_file():
        candidate_region = json.loads(case.candidate_manifest.read_text("utf-8"))
    volumetry_structures = [
        VolumetryStructure(
            role=str(item["role"]),
            label=str(item["label"]),
            mask_path=Path(next(spec["mask"] for spec in plan if spec["role"] == item["role"])),
            material=str(item["material"]),
        )
        for item in items
    ]
    volumetry = build_volumetry_manifest(
        reference_volume=case.volume,
        structures=volumetry_structures,
        output_dir=case.outputs,
        case_id=manifest.get("case_id"),
        segmentation_quality=(
            case.segmentation_quality_manifest_v2
            if case.segmentation_quality_manifest_v2.is_file()
            else None
        ),
    )
    viewer = {
        "schema": "argos-viewer-manifest-v2",
        "schema_version": 2,
        "case_id": manifest.get("case_id"),
        "organ": profile["id"],
        "coordinate_system": profile.get("exportacao", {}).get(
            "sistema_coordenadas", "LPS"
        ),
        "regulatory_state": manifest.get("regulatory_state", "PESQUISA"),
        "disclaimer": "Uso em pesquisa/educação. NÃO destinado a decisão clínica.",
        "quality_scope": (
            "Fidelidade da reconstrução à máscara fonte; não mede acurácia "
            "anatômica da segmentação."
        ),
        "acquisition": acquisition,
        "meshes": items,
        "reference_images": reference_images,
        "spatial_relationships": relationships,
        "lesion_context": lesion_context,
        "candidate_context": candidate_context,
        "candidate_region": candidate_region,
        "volumetry": volumetry,
        "viewer_features": {
            "default_visual_preset": "default",
            "orthogonal_clipping": True,
            "surface_distance_measurement": True,
            "wireframe_inspection": True,
            "reference_mr_stack": True,
            "screenshot": True,
            "unconfirmed_candidate_review": candidate_region is not None,
            "physical_mask_volumetry": True,
            "webxr": True,
            "webxr_schema": "oren-webxr-viewer-v1",
            "webxr_modes": ["immersive-vr", "immersive-ar"],
            "webxr_optional_features": ["local-floor", "hand-tracking"],
            "webxr_measurement_authority": "binary_mask_in_physical_space",
        },
        "review_requirements": {
            "inspect_3d_contour": True,
            "inspect_2d_reference": True,
            "acknowledge_research_only": True,
            "inspect_candidate_against_mr": bool(
                candidate_region and candidate_region.get("candidate_present")
            ),
        },
    }
    temp_manifest = viewer_manifest_path.with_name(".viewer_manifest.json.tmp")
    temp_manifest.write_text(
        json.dumps(viewer, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temp_manifest.replace(viewer_manifest_path)
    log.info(
        "Estágio 7: manifesto do visualizador escrito em %s",
        viewer_manifest_path,
    )
