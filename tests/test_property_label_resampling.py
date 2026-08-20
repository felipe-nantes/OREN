"""Property + audit tests — GEO-LABEL-01 (PHASE_04_INVARIANTS).

Contrato (`.fable/CONTRACTS.md`, `GEO-LABEL-01`): "resampling de labels
discretos usa nearest-neighbor e não inventa classes; todo uso deve ser
verificado por rota."

Este arquivo cobre as duas metades do contrato:

1. **O invariante em si** (property, via Hypothesis): reamostragem
   nearest-neighbor de um mapa de labels nunca produz um valor que não
   existia na entrada. O contraste com interpolação linear — que *inventa*
   classes intermediárias — prova que o invariante não é trivial.
2. **"todo uso deve ser verificado por rota"** (auditoria estrutural): varre
   por AST todos os call sites de resample em `dtwin/` e falha se aparecer um
   novo módulo usando interpolação contínua fora da allowlist revisada. Um
   `sitk.Resample` novo sobre máscara, com o interpolador errado, quebra aqui.

Auditoria exaustiva de 2026-08-18 (TASK-2026-08-18-PH04-INV-02): 28 call sites
inspecionados, zero violações.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

ROOT = Path(__file__).resolve().parents[1]
SHAPE = (4, 5, 6)  # (z, y, x)

# Módulos onde interpolação CONTÍNUA (linear) é legítima porque o dado
# reamostrado não é um label discreto. Cada entrada foi verificada na
# auditoria de 2026-08-18; adicionar um módulo aqui exige revisão de rota
# (GEOMETRY) e é o ponto em que este teste força a discussão.
INTERPOLACAO_CONTINUA_AUTORIZADA = {
    # intensidade de fase (float32), não label
    "dtwin/benchmark/liverhccseg_preparation.py",
    "dtwin/benchmark/lld_mmri_v23_harmonization.py",
    "dtwin/benchmark/openswisshcc_alignment.py",
    "dtwin/learning/multiphase_ingest.py",
    # volume de intensidade publicado para o viewer
    "dtwin/viewer_artifacts.py",
    # campo de distância com sinal (contínuo por construção, via
    # SignedMaurerDistanceMap) -- interpolar aqui é justamente o que remove o
    # terraceamento da malha; ver dtwin/stages.py::_campo_continuo
    "dtwin/stages.py",
}

_INTERPOLADORES_CONTINUOS = {"sitkLinear", "sitkBSpline", "sitkGaussian", "sitkHammingWindowedSinc"}


def _grade_alvo(referencia: sitk.Image, fator: float) -> sitk.Image:
    """Grade com espaçamento diferente -> força reamostragem real."""
    alvo = sitk.Image(
        [max(1, int(round(t * fator))) for t in referencia.GetSize()],
        referencia.GetPixelID(),
    )
    alvo.SetOrigin(referencia.GetOrigin())
    alvo.SetDirection(referencia.GetDirection())
    alvo.SetSpacing([s / fator for s in referencia.GetSpacing()])
    return alvo


@settings(max_examples=150, deadline=None)
@given(
    labels=arrays(dtype=np.uint8, shape=SHAPE, elements=st.integers(min_value=0, max_value=6)),
    fator=st.sampled_from([0.5, 1.5, 2.0, 3.0]),
)
def test_property_nearest_neighbor_nunca_inventa_classe(labels, fator):
    """GEO-LABEL-01: para qualquer mapa de labels e qualquer mudança de grade,
    nearest-neighbor só devolve valores que já existiam na entrada (ou o valor
    default 0 nas bordas fora do suporte). Nunca uma classe nova."""
    origem = sitk.GetImageFromArray(labels)
    origem.SetSpacing((1.0, 1.0, 1.0))
    alvo = _grade_alvo(origem, fator)

    saida = sitk.Resample(
        origem, alvo, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8
    )

    classes_entrada = set(np.unique(labels).tolist()) | {0}  # 0 = default fora do suporte
    classes_saida = set(np.unique(sitk.GetArrayFromImage(saida)).tolist())
    assert classes_saida <= classes_entrada, (
        f"nearest-neighbor inventou classes: {sorted(classes_saida - classes_entrada)}"
    )


def test_interpolacao_linear_inventa_classes_e_por_isso_e_proibida_em_labels():
    """Contraste que torna GEO-LABEL-01 não-trivial: com os MESMOS dados, a
    interpolação linear fabrica classes intermediárias que nunca existiram.
    É exatamente o modo de falha que o contrato proíbe."""
    labels = np.zeros(SHAPE, dtype=np.uint8)
    labels[:, :, :3] = 0
    labels[:, :, 3:] = 6  # fronteira dura entre duas classes distantes

    origem = sitk.GetImageFromArray(labels)
    origem.SetSpacing((1.0, 1.0, 1.0))
    alvo = _grade_alvo(origem, 3.0)

    nearest = sitk.Resample(
        origem, alvo, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8
    )
    linear = sitk.Resample(
        origem, alvo, sitk.Transform(), sitk.sitkLinear, 0, sitk.sitkUInt8
    )

    classes_validas = {0, 6}
    classes_nearest = set(np.unique(sitk.GetArrayFromImage(nearest)).tolist())
    classes_linear = set(np.unique(sitk.GetArrayFromImage(linear)).tolist())

    assert classes_nearest <= classes_validas
    assert classes_linear - classes_validas, (
        "a interpolação linear deveria ter fabricado classes intermediárias "
        "neste cenário -- se não fabricou, o teste de contraste perdeu o sentido"
    )


def _call_sites_de_resample() -> dict[str, set[str]]:
    """Mapeia módulo -> interpoladores usados em REAMOSTRAGEM, via AST.

    Cobre exatamente dois padrões, e só eles:

    - `sitk.Resample(...)` — interpolador posicional ou nomeado;
    - `<var>.SetInterpolator(...)` **apenas** quando `<var>` foi atribuída de
      `sitk.ResampleImageFilter()`.

    A segunda restrição importa: `ImageRegistrationMethod.SetInterpolator`
    também existe no código, mas define como a MÉTRICA de similaridade é
    avaliada sobre intensidade contínua durante o registro — não reamostra
    label nenhum. Confundir os dois transformaria esta auditoria em ruído e
    forçaria allowlists falsas (verificado em
    `dtwin/learning/monophase_complementary_candidates.py:137`, onde o
    registro usa linear na métrica e o resample da máscara, logo abaixo, usa
    nearest-neighbor corretamente).
    """
    encontrados: dict[str, set[str]] = {}
    for arquivo in sorted((ROOT / "dtwin").rglob("*.py")):
        if "__pycache__" in arquivo.parts:
            continue
        try:
            arvore = ast.parse(arquivo.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:  # pragma: no cover - defensivo
            continue
        relativo = arquivo.relative_to(ROOT).as_posix()

        filtros_de_resample: set[str] = set()
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.Assign)
                and isinstance(no.value, ast.Call)
                and isinstance(no.value.func, ast.Attribute)
                and no.value.func.attr == "ResampleImageFilter"
            ):
                for alvo in no.targets:
                    if isinstance(alvo, ast.Name):
                        filtros_de_resample.add(alvo.id)

        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
                continue
            eh_resample_direto = no.func.attr == "Resample"
            eh_set_interpolator_de_filtro = (
                no.func.attr == "SetInterpolator"
                and isinstance(no.func.value, ast.Name)
                and no.func.value.id in filtros_de_resample
            )
            if not (eh_resample_direto or eh_set_interpolator_de_filtro):
                continue
            for interno in ast.walk(no):
                if isinstance(interno, ast.Attribute) and interno.attr.startswith("sitk"):
                    encontrados.setdefault(relativo, set()).add(interno.attr)
    return encontrados


def test_auditoria_todo_resample_de_label_usa_nearest_neighbor():
    """GEO-LABEL-01, metade "todo uso deve ser verificado por rota": nenhum
    módulo pode usar interpolação contínua em resample sem estar na allowlist
    revisada. Um call site novo sobre máscara falha aqui e força revisão."""
    call_sites = _call_sites_de_resample()
    assert call_sites, "auditoria não encontrou nenhum call site -- varredura quebrada"

    modulos_com_interpolacao_continua = {
        modulo
        for modulo, interpoladores in call_sites.items()
        if interpoladores & _INTERPOLADORES_CONTINUOS
    }

    nao_revisados = modulos_com_interpolacao_continua - INTERPOLACAO_CONTINUA_AUTORIZADA
    assert not nao_revisados, (
        "módulo(s) usando interpolação contínua em resample sem revisão de rota "
        f"(GEO-LABEL-01): {sorted(nao_revisados)}. Se o dado for contínuo "
        "(intensidade/campo de distância), documente e adicione à allowlist; se "
        "for label discreto, use sitkNearestNeighbor."
    )


def test_auditoria_allowlist_nao_tem_entrada_obsoleta():
    """A allowlist não pode acumular entradas mortas: cada módulo autorizado
    tem de continuar existindo e realmente usando interpolação contínua."""
    call_sites = _call_sites_de_resample()
    for modulo in INTERPOLACAO_CONTINUA_AUTORIZADA:
        assert (ROOT / modulo).is_file(), f"allowlist cita módulo inexistente: {modulo}"
        interpoladores = call_sites.get(modulo, set())
        assert interpoladores & _INTERPOLACAO_CONTINUA_ESPERADA_EM.get(modulo, _INTERPOLADORES_CONTINUOS), (
            f"{modulo} está na allowlist mas não usa mais interpolação contínua; "
            "remova a entrada para a allowlist não mascarar um call site futuro"
        )


# Permite ser específico por módulo no futuro; hoje todos usam sitkLinear.
_INTERPOLACAO_CONTINUA_ESPERADA_EM: dict[str, set[str]] = {}
