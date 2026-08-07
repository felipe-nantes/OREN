# tests/test_engine_finalize.py
import json
from pathlib import Path

import numpy as np
from PIL import Image

from dtwin.engine import Engine
from dtwin.core import array_from, array_to_image, read_image, save_image, sha256_of
from .conftest import make_sphere_mask


def test_finalize_produces_stls_and_manifest(synthetic_case):
    engine = Engine(Path("profiles/figado.yaml"))
    case = engine.finalize(str(synthetic_case.root), no_lesion=False)

    organ_stl = case.outputs / "figado_orgao.stl"
    lesion_stl = case.outputs / "figado_lesao.stl"
    manifest = case.outputs / "viewer_manifest.json"
    assert organ_stl.exists() and organ_stl.stat().st_size > 0
    assert lesion_stl.exists() and lesion_stl.stat().st_size > 0
    assert manifest.exists()

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["schema"] == "argos-viewer-manifest-v2"
    assert data["schema_version"] == 2
    assert data["organ"] == "figado"
    assert data["coordinate_system"] == "LPS"
    roles = {m["role"]: m for m in data["meshes"]}
    assert set(roles) == {"orgao", "lesao"}
    # STL refs are relative filenames only (viewer depends on this)
    for m in data["meshes"]:
        assert "/" not in m["stl"] and "\\" not in m["stl"]
        assert (case.outputs / m["stl"]).exists()
        metrics = m["metrics"]
        assert metrics["not_segmentation_accuracy"] is True
        assert metrics["source_mask_volume_ml"] > 0
        assert metrics["mesh_sha256"] == sha256_of(case.outputs / m["stl"])
        assert metrics["vertices"] > 0 and metrics["triangles"] > 0

    references = data["reference_images"]
    assert references["contains_phi_metadata"] is False
    axial = references["views"]["axial"]
    mask = array_from(read_image(case.mask_organ_clean)) > 0
    expected_indices = np.flatnonzero(mask.any(axis=(1, 2))).tolist()
    assert [frame["index"] for frame in axial["frames"]] == expected_indices
    assert axial["coverage"] == "all_liver_bearing_planes"
    for view in references["views"].values():
        for frame in view["frames"]:
            image_path = case.outputs / frame["file"]
            assert image_path.is_file()
            assert frame["sha256"] == sha256_of(image_path)
            with Image.open(image_path) as image:
                assert image.size == (512, 512)
                assert not image.getexif()


def test_finalize_no_lesion_flag(synthetic_case):
    # remove the lesion mask, finalize with --no-lesion
    synthetic_case.mask_lesion.unlink()
    engine = Engine(Path("profiles/figado.yaml"))
    case = engine.finalize(str(synthetic_case.root), no_lesion=True)
    data = json.loads((case.outputs / "viewer_manifest.json").read_text(encoding="utf-8"))
    roles = {m["role"] for m in data["meshes"]}
    assert "orgao" in roles
    assert "lesao" not in roles


def test_refinalize_no_lesion_drops_prior_lesion(synthetic_case):
    """Re-running finalize with --no-lesion after a lesion run must not keep the
    stale lesion mesh/STL. Finalize has to be idempotent against prior artifacts."""
    engine = Engine(Path("profiles/figado.yaml"))
    # first pass: real lesion present
    case = engine.finalize(str(synthetic_case.root), no_lesion=False)
    assert (case.outputs / "figado_lesao.stl").exists()

    # operator decides there is no lesion: drop the mask, re-finalize
    synthetic_case.mask_lesion.unlink()
    case = engine.finalize(str(synthetic_case.root), no_lesion=True)

    data = json.loads((case.outputs / "viewer_manifest.json").read_text(encoding="utf-8"))
    roles = {m["role"] for m in data["meshes"]}
    assert "lesao" not in roles, "stale lesion survived a --no-lesion re-finalize"
    assert not (case.outputs / "figado_lesao.stl").exists()
    assert not case.mesh_lesion.exists()


def test_finalize_exports_internal_anatomy_when_available(synthetic_case):
    """Anatomia interna é publicada com metadados para o viewer, sem atlas externo."""
    ref = read_image(synthetic_case.mask_organ)
    shape = tuple(reversed(ref.GetSize()))
    for role, center in (("couinaud_i", (20, 16, 20)), ("vesicula_biliar", (25, 23, 20))):
        mask = make_sphere_mask(shape, center, 4)
        save_image(array_to_image(mask, ref), synthetic_case.anatomy_mask(role))

    case = Engine(Path("profiles/figado.yaml")).finalize(str(synthetic_case.root), no_lesion=False)
    data = json.loads((case.outputs / "viewer_manifest.json").read_text(encoding="utf-8"))
    roles = {item["role"]: item for item in data["meshes"]}

    assert {"orgao", "lesao", "couinaud_i", "vesicula_biliar"} <= set(roles)
    assert roles["couinaud_i"]["label"] == "Segmento Couinaud I"
    assert roles["couinaud_i"]["material"] == "segment"
    assert roles["orgao"]["default_visible"] is False
    assert (case.outputs / roles["couinaud_i"]["stl"]).is_file()


def test_isolar_orgao_remove_ilha_quando_o_corpo_principal_domina():
    """Ilhas soltas viram objetos flutuando no visualizador (docs/188)."""
    import numpy as np
    from dtwin.stages import _isolar_orgao_para_visualizacao

    volume = np.zeros((20, 20, 20), dtype=bool)
    volume[5:15, 5:15, 5:15] = True          # corpo principal
    volume[1, 1, 1] = True                    # ilha de 1 voxel
    limpo, diagnostico = _isolar_orgao_para_visualizacao(volume)
    assert diagnostico["isolado"] is True
    assert diagnostico["componentes"] == 2
    assert limpo[1, 1, 1] == 0
    assert int(limpo.sum()) == 1000


def test_isolar_orgao_preserva_tudo_quando_o_figado_esta_partido():
    """A guarda existe para não apagar anatomia: dois pedaços grandes ficam."""
    import numpy as np
    from dtwin.stages import _isolar_orgao_para_visualizacao

    volume = np.zeros((30, 30, 30), dtype=bool)
    volume[2:12, 2:12, 2:12] = True           # 1000 voxels
    volume[18:28, 18:28, 18:28] = True        # 1000 voxels — fração 0,5
    limpo, diagnostico = _isolar_orgao_para_visualizacao(volume)
    assert diagnostico["isolado"] is False
    assert diagnostico["motivo"] == "orgao_partido_isolar_apagaria_anatomia"
    assert int(limpo.sum()) == 2000, "não pode apagar metade do órgão"


def test_isolar_orgao_preenche_cavidade_interna():
    import numpy as np
    from dtwin.stages import _isolar_orgao_para_visualizacao

    volume = np.zeros((20, 20, 20), dtype=bool)
    volume[5:15, 5:15, 5:15] = True
    volume[9:11, 9:11, 9:11] = False          # cavidade interna
    limpo, _ = _isolar_orgao_para_visualizacao(volume)
    assert int(limpo.sum()) == 1000, "cavidade deveria ser preenchida"


def test_preencher_cavidade_nao_desfaz_a_guarda_do_figado_partido():
    """Preencher buracos não pode fundir dois pedaços grandes num só."""
    import numpy as np
    from dtwin.stages import _isolar_orgao_para_visualizacao

    volume = np.zeros((30, 30, 30), dtype=bool)
    volume[2:12, 2:12, 2:12] = True
    volume[18:28, 18:28, 18:28] = True
    limpo, diagnostico = _isolar_orgao_para_visualizacao(volume)
    assert diagnostico["isolado"] is False
    assert int(limpo.sum()) == 2000
    from scipy import ndimage
    assert ndimage.label(limpo)[1] == 2, "os dois pedaços devem continuar separados"


def test_fonte_da_malha_prefere_uniao_quando_disponivel(tmp_path):
    """docs/188 §9, docs/189: a visualização prefere a união; a classificação
    nunca chama esta função e nunca lê mask_organ_union.nii.gz."""
    import SimpleITK as sitk

    from dtwin.core import Case
    from dtwin.stages import _fonte_da_malha_do_orgao

    case = Case(root=tmp_path)
    imagem = sitk.GetImageFromArray(make_sphere_mask((20, 20, 20), (10, 10, 10), 5).astype(np.uint8))
    sitk.WriteImage(imagem, str(case.mask_organ))
    assert _fonte_da_malha_do_orgao(case) == case.mask_organ, "sem união, cai para a venosa"

    sitk.WriteImage(imagem, str(case.mask_organ_union))
    assert _fonte_da_malha_do_orgao(case) == case.mask_organ_union, "com união, prefere a união"


def test_estagio5_descarta_uniao_com_geometria_divergente(tmp_path):
    """Um arquivo de união corrompido/deslocado não pode deformar a malha em
    silêncio -- o estágio volta para a venosa (referência garantida)."""
    import SimpleITK as sitk

    from dtwin.core import Case
    from dtwin.stages import stage5_refine

    case = Case(root=tmp_path)
    venosa = make_sphere_mask((20, 20, 20), (10, 10, 10), 6).astype(np.uint8)
    img_venosa = sitk.GetImageFromArray(venosa)
    img_venosa.SetSpacing((1.0, 1.0, 1.0))
    sitk.WriteImage(img_venosa, str(case.mask_organ))

    # União com espaçamento diferente -- geometria divergente de propósito.
    uniao_divergente = sitk.GetImageFromArray(venosa)
    uniao_divergente.SetSpacing((2.0, 2.0, 2.0))
    sitk.WriteImage(uniao_divergente, str(case.mask_organ_union))

    lesao_vazia = sitk.GetImageFromArray(np.zeros((20, 20, 20), dtype=np.uint8))
    lesao_vazia.CopyInformation(img_venosa)
    sitk.WriteImage(lesao_vazia, str(case.mask_lesion))

    stage5_refine(case, {"refino": {}})

    resultado = sitk.GetArrayFromImage(sitk.ReadImage(str(case.mask_organ_clean))) > 0
    volume_venosa = int(venosa.sum())
    # Descartou a união (que tinha o dobro do espaçamento -> volume físico 8x
    # maior) e refinou a partir da venosa -- o volume em voxels bate com ela,
    # não com uma malha distorcida.
    assert abs(int(resultado.sum()) - volume_venosa) < volume_venosa * 0.2


def test_regiao_classificada_so_existe_quando_ha_uniao(tmp_path):
    """Sem união, a região classificada seria idêntica ao órgão inteiro --
    overlay sobre si mesmo, ruído puro (docs/189 §5.2)."""
    import SimpleITK as sitk

    from dtwin.core import Case
    from dtwin.stages import stage5_refine

    case = Case(root=tmp_path)
    esfera = make_sphere_mask((20, 20, 20), (10, 10, 10), 6).astype(np.uint8)
    img = sitk.GetImageFromArray(esfera)
    sitk.WriteImage(img, str(case.mask_organ))
    lesao_vazia = sitk.GetImageFromArray(np.zeros((20, 20, 20), dtype=np.uint8))
    lesao_vazia.CopyInformation(img)
    sitk.WriteImage(lesao_vazia, str(case.mask_lesion))

    stage5_refine(case, {"refino": {}})

    assert not case.mask_organ_classified_region_clean.is_file(), (
        "sem união, não deveria existir overlay -- seria idêntico ao órgão"
    )


def test_regiao_classificada_fica_contida_no_orgao_da_uniao(tmp_path):
    """A garantia central do overlay: união ⊇ venosa por construção, e o
    overlay tem que respeitar isso geometricamente, não só em teoria."""
    import SimpleITK as sitk

    from dtwin.core import Case
    from dtwin.stages import stage5_refine

    case = Case(root=tmp_path)
    venosa = make_sphere_mask((30, 30, 30), (15, 15, 15), 6).astype(np.uint8)
    uniao = make_sphere_mask((30, 30, 30), (15, 15, 15), 9).astype(np.uint8)  # maior, contém a venosa
    img_venosa = sitk.GetImageFromArray(venosa)
    sitk.WriteImage(img_venosa, str(case.mask_organ))
    img_uniao = sitk.GetImageFromArray(uniao)
    img_uniao.CopyInformation(img_venosa)
    sitk.WriteImage(img_uniao, str(case.mask_organ_union))
    lesao_vazia = sitk.GetImageFromArray(np.zeros((30, 30, 30), dtype=np.uint8))
    lesao_vazia.CopyInformation(img_venosa)
    sitk.WriteImage(lesao_vazia, str(case.mask_lesion))

    stage5_refine(case, {"refino": {}})

    assert case.mask_organ_classified_region_clean.is_file()
    regiao = sitk.GetArrayFromImage(sitk.ReadImage(str(case.mask_organ_classified_region_clean))) > 0
    orgao = sitk.GetArrayFromImage(sitk.ReadImage(str(case.mask_organ_clean))) > 0
    assert not (regiao & ~orgao).any(), "a região classificada vazou para fora do órgão exibido"
    assert regiao.sum() < orgao.sum(), "a região classificada deveria ser um subconjunto próprio"


def test_regiao_classificada_e_removida_quando_a_execucao_deixa_de_ter_uniao(tmp_path):
    """finalize precisa ser idempotente: uma execução sem união não pode
    republicar o overlay de uma execução anterior que teve união."""
    import SimpleITK as sitk

    from dtwin.core import Case
    from dtwin.stages import stage5_refine

    case = Case(root=tmp_path)
    venosa = make_sphere_mask((20, 20, 20), (10, 10, 10), 6).astype(np.uint8)
    img = sitk.GetImageFromArray(venosa)
    sitk.WriteImage(img, str(case.mask_organ))
    lesao_vazia = sitk.GetImageFromArray(np.zeros((20, 20, 20), dtype=np.uint8))
    lesao_vazia.CopyInformation(img)
    sitk.WriteImage(lesao_vazia, str(case.mask_lesion))
    # Simula um overlay fantasma deixado por uma execução anterior.
    case.mask_organ_classified_region_clean.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(img, str(case.mask_organ_classified_region_clean))

    stage5_refine(case, {"refino": {}})

    assert not case.mask_organ_classified_region_clean.is_file()
