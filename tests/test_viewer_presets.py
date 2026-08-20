from pathlib import Path

import pytest
from pydantic import ValidationError

from webapp import server

ROOT = Path(__file__).resolve().parents[1]


def test_viewer_exposes_reproducible_visual_presets_without_new_inference():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")

    for preset in ("default", "anatomy", "triage", "segments"):
        assert f"{preset}: {{" in source
    assert "realistic: {" not in source
    assert 'label: "Tecido realista"' not in source
    assert "function applyPreset(name)" in source
    assert 'const DEFAULT_VISUAL_PRESET = "default"' in source
    assert "function applyInitialPreset(manifest)" in source
    assert "applyInitialPreset(manifest);" in source
    assert "active_preset: currentPreset" in source


def test_rendering_profile_toggle_preserves_protected_baseline_contract():
    source = Path("viewer/app.js").read_text("utf-8")
    assert 'const SCIENTIFIC_CURRENT_PROFILE = "scientific_current_v1"' in source
    assert 'const ANATOMIC_REALISTIC_PROFILE = "anatomic_realistic_v1"' in source
    assert "function setRenderingProfile(name, options = {})" in source
    assert "function toggleRenderingProfile()" in source
    assert '"Ativar textura realista"' in source
    assert '"Desativar textura realista"' in source
    assert "applyScientificCurrentAppearance" in source
    assert "applyAnatomicRealisticAppearance" in source
    assert "mesh.userData.targetOpacity = opacity" in source
    assert "mesh.visible = visible" in source
    assert 'const REALISTIC_MATERIAL_PACK_ID = "oren-liver-realistic-v1"' in source
    assert 'const RENDERING_QUALITY_TIERS = Object.freeze(["quality", "stability"])' in source
    assert "function setRenderingQualityTier" in source
    assert "displacementMap" not in source

    apply_body = source.split("function applyPreset(name)", 1)[1].split("function buildControls", 1)[0]
    assert "fetch(" not in apply_body
    assert "animateMeshVisibility" in apply_body
    assert "syncStructureControl" in apply_body


def test_segments_preset_requires_segment_meshes():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")

    assert "requiresSegments: true" in source
    assert "button.disabled = true" in source
    assert "Segmentos de Couinaud" in source
    assert "REQUIRED_COUINAUD_ROLES.every" in source
    assert "function applySegmentAtlasAppearance(item, mesh)" in source
    assert '["organ", "segment", "vessel", "gallbladder"].includes(category)' in source
    segments_state = source.split('if (presetName === "segments")', 1)[1].split(
        "return { visible, opacity };", 1
    )[0]
    assert "segment: 1.0" in segments_state
    assert "solidSurface && value >= 0.999" in source
    assert '["organ", "segment", "vessel", "gallbladder"].includes(category)' in source
    assert "mesh.material.transparent = !fullyOpaque" in source
    assert "mesh.material.depthWrite = fullyOpaque" in source
    assert "organ: 1.0, vessel: 1.0, gallbladder: 1.0" in source
    assert "organ: 0.30, vessel: 1.0, gallbladder: 1.0" in source


def test_viewer_state_accepts_only_known_visual_presets():
    state = server.ViewerStatePayload(
        active_preset="default",
        rendering_profile="anatomic_realistic_v1",
        rendering_quality_tier="stability",
        material_pack_id="oren-liver-realistic-v1",
        material_pack_variant="quest512",
        rendering_fallback_reason="performance_budget_exceeded",
    )
    assert state.active_preset == "default"
    assert state.rendering_profile == "anatomic_realistic_v1"
    assert state.rendering_quality_tier == "stability"
    assert state.material_pack_id == "oren-liver-realistic-v1"
    assert state.material_pack_variant == "quest512"
    assert state.rendering_fallback_reason == "performance_budget_exceeded"

    # Compatibilidade com revisões históricas, sem reexpor o modo na interface.
    assert server.ViewerStatePayload(active_preset="realistic").active_preset == "realistic"

    with pytest.raises(ValidationError):
        server.ViewerStatePayload(active_preset="../../arbitrary")
    with pytest.raises(ValidationError):
        server.ViewerStatePayload(rendering_profile="../../arbitrary")
    with pytest.raises(ValidationError):
        server.ViewerStatePayload(rendering_quality_tier="ultra")
    with pytest.raises(ValidationError):
        server.ViewerStatePayload(material_pack_id="remote-or-arbitrary")
    with pytest.raises(ValidationError):
        server.ViewerStatePayload(material_pack_variant="4k-unbounded")
    with pytest.raises(ValidationError):
        server.ViewerStatePayload(rendering_fallback_reason="silent-or-unknown")


def test_realistic_tissue_is_the_default_visual_language_and_respects_occlusion():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")

    assert "function applyHepaticTissueAppearance(mesh)" in source
    assert "function restoreMaterialAppearance(mesh)" in source
    assert 'presetName === "realistic"' not in source
    assert "function configureOpacityOcclusion(item, mesh, opacity)" in source
    appearance_body = source.split("function applyHepaticTissueAppearance(mesh)", 1)[1].split(
        "function applyMaterialProfile", 1
    )[0]
    assert "fetch(" not in appearance_body
    assert "mask" not in appearance_body.lower()
    assert "geometry.setAttribute" in appearance_body
    assert "function applyAnatomicalOverlayAppearance(item, mesh)" in source
    overlay_body = source.split("function applyAnatomicalOverlayAppearance(item, mesh)", 1)[1].split(
        "function applyHepaticTissueAppearance", 1
    )[0]
    assert "fetch(" not in overlay_body
    assert "depthTest = true" in overlay_body
    assert 'category === "vessel"' in overlay_body
    assert 'category === "gallbladder"' in overlay_body
    assert "function applyOrganicVertexTone" in source
    assert "0x3d526f" in overlay_body
    assert "0x356b72" in overlay_body
    assert "0x53653d" in overlay_body
    assert "0xa86125" in overlay_body
    occlusion_body = source.split("function configureOpacityOcclusion", 1)[1].split(
        "function applySegmentAtlasAppearance", 1
    )[0]
    assert "value >= 0.999" in occlusion_body
    assert "material.depthTest = true" in occlusion_body


def test_reference_frames_synchronize_to_orthogonal_3d_clipping_without_inference():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")

    assert 'const REFERENCE_CLIP_AXES = Object.freeze({ axial: "z", coronal: "y", sagittal: "x" })' in source
    assert "function syncReferenceToClipping" in source
    assert "position_lps_mm" in source
    assert "sourceBounds.min[axis]" in source
    assert "sourceBounds.max[axis]" in source
    assert "reference_sync_enabled: referenceSync.checked" in source
    assert "reference_frame_index: Number(referenceSlider.value)" in source
    sync_body = source.split("function syncReferenceToClipping", 1)[1].split(
        "function selectReferenceView", 1
    )[0]
    assert "fetch(" not in sync_body
    assert "clipEnabled.checked = true" in sync_body
    assert "THREE.MathUtils.clamp" in sync_body


def test_viewer_state_validates_reference_sync_fields():
    state = server.ViewerStatePayload(
        reference_sync_enabled=True,
        reference_view="coronal",
        reference_frame_index=12,
    )
    assert state.reference_view == "coronal"
    assert state.reference_frame_index == 12

    with pytest.raises(ValidationError):
        server.ViewerStatePayload(reference_view="oblique")
    with pytest.raises(ValidationError):
        server.ViewerStatePayload(reference_frame_index=-1)


def test_remote_viewer_loads_liver_first_and_references_lazily():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")

    assert "async function loadRemoteManifestProgressively(base, manifest)" in source
    assert "async function fetchMeshBuffersBounded" in source
    assert "concurrency = 3" in source
    assert 'meshCategory(item) === "organ"' in source
    assert "meshes: [organ]" in source
    assert "{ complete: false }" in source
    assert "referenceBaseUrl: base" in source
    assert "referenceFileMap: {}" in source
    assert "function prepareIncrementalMesh(item, buffer)" in source
    assert "await nextAnimationFrame()" in source
    assert "finalizeManifestPresentation(manifest, {}, {" in source
    assert "animate: false" in source
    assert "return remoteArtifactUrl(referenceBaseUrl, filename)" in source
    assert "function referenceFilenames" not in source
    assert "Aguarde o carregamento completo das estruturas 3D." in source
    assert "getLoadingState: () => ({ ...loadingState })" in source


def test_structure_selection_is_visual_auditable_and_does_not_replace_measurement():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")

    assert "function selectStructure(role, options = {})" in source
    assert "function clearStructureSelection" in source
    assert "structureCategoryLabel(item)" in source
    assert "metrics.source_mask_volume_ml" in source
    assert "metrics.surface_area_cm2" in source
    assert "metrics.watertight_and_manifold" in source
    assert "não acurácia anatômica" in source
    assert "if (!measurementEnabled)" in source
    assert "selected_role: selectedRole" in source
    select_body = source.split("function selectStructure(role, options = {})", 1)[1].split(
        "function renderQuality", 1
    )[0]
    assert "fetch(" not in select_body
    assert "emissive.setHex(0x2daf79)" in select_body


def test_viewer_state_validates_selected_structure_role():
    assert server.ViewerStatePayload(selected_role="couinaud_viii").selected_role == "couinaud_viii"
    assert server.ViewerStatePayload(selected_role=None).selected_role is None

    with pytest.raises(ValidationError):
        server.ViewerStatePayload(selected_role="../../arquivo")


def test_selected_structure_has_contextual_focus_isolation_and_restore_actions():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "viewer" / "index.html").read_text(encoding="utf-8")

    assert 'id="selection-focus"' in html
    assert 'id="selection-isolate"' in html
    assert 'id="selection-context"' in html
    assert "function focusSelectedStructure()" in source
    assert "targets.forEach((mesh) => bounds.expandByObject(mesh))" in source
    assert "function isolateSelectedStructure()" in source
    assert "function restoreSelectedContext()" in source
    assert "selectionContextPreset" in source
    assert "selection_isolated: selectionIsolated" in source
    assert "fetch(" not in source.split("function focusSelectedStructure()", 1)[1].split(
        "function isolateSelectedStructure()", 1
    )[0]

    state = server.ViewerStatePayload(
        active_view="focus", selected_role="couinaud_viii", selection_isolated=True
    )
    assert state.active_view == "focus"
    assert state.selection_isolated is True


def test_anatomical_quick_views_are_fixed_and_do_not_request_new_inference():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "viewer" / "index.html").read_text(encoding="utf-8")

    for name in ("liver", "segments", "vascular", "candidate"):
        assert f'data-anatomical-view="{name}"' in html
        assert f"{name}: {{" in source
    assert "function applyAnatomicalView(name)" in source
    assert "function anatomicalViewAvailable(name)" in source
    assert 'viewName: "anatomical"' in source
    body = source.split("function applyAnatomicalView(name)", 1)[1].split(
        "function currentVisibleRoles", 1
    )[0]
    assert "fetch(" not in body
    assert "applyPreset(definition.preset)" in body
    assert "focusMeshRoles" in body

    state = server.ViewerStatePayload(active_view="anatomical", active_anatomical_view="vascular")
    assert state.active_anatomical_view == "vascular"


def test_saved_review_views_capture_reproducible_visual_state():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")

    assert "function saveCurrentView()" in source
    assert "function restoreSavedView(bookmarkId)" in source
    assert "camera_position_mm: camera.position.toArray()" in source
    assert "camera_target_mm: orbit.target.toArray()" in source
    assert "opacity_by_role: opacityByRole" in source
    assert "saved_views: savedViews.slice(0, MAX_SAVED_VIEWS).map(savedViewPayload)" in source
    restore_body = source.split("function restoreSavedView(bookmarkId)", 1)[1].split(
        "function removeSavedView", 1
    )[0]
    assert "fetch(" not in restore_body
    assert "updateClipping()" in restore_body
    assert "selectReferenceView" in restore_body
    assert "animateMeshVisibility" in restore_body

    saved = server.ViewerSavedViewPayload(
        bookmark_id="view-001",
        label="Vista 1 · Fígado",
        active_view="anatomical",
        active_preset="default",
        active_anatomical_view="liver",
        material_profile="default",
        selected_role="orgao",
        camera_position_mm=[1.0, 2.0, 3.0],
        camera_target_mm=[0.0, 0.0, 0.0],
        visible_roles=["orgao"],
        opacity_by_role={"orgao": 1.0},
    )
    assert saved.bookmark_id == "view-001"
    assert saved.camera_position_mm == [1.0, 2.0, 3.0]

    with pytest.raises(ValidationError):
        server.ViewerSavedViewPayload(
            bookmark_id="arbitrary",
            label="Vista",
            camera_position_mm=[1.0, 2.0, 3.0],
            camera_target_mm=[0.0, 0.0, 0.0],
        )


def test_selected_mesh_can_be_measured_in_three_lps_dimensions():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "viewer" / "index.html").read_text(encoding="utf-8")

    assert 'id="selection-dimensions"' in html
    assert "function measureSelectedStructure3d()" in source
    assert "mesh.geometry.computeBoundingBox()" in source
    assert "item.metrics?.dimensions_mm" in source
    assert '"source_binary_mask_axis_aligned_lps_bounding_box"' in source
    assert '"source_binary_mask_metrics"' in source
    assert "approximate: !dimensionsFromMask" in source
    assert "structure_dimensions_3d: structureMeasurements3d.slice(0, 16)" in source
    body = source.split("function measureSelectedStructure3d()", 1)[1].split(
        "function anatomicalTargetRoles", 1
    )[0]
    assert "fetch(" not in body
    assert "dimensionGuide" in body


def test_clipping_plane_follows_xr_model_transform_and_preserves_anatomy():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")
    xr = (ROOT / "viewer" / "xr.js").read_text(encoding="utf-8")

    assert "const localClippingPlane" in source
    assert "function refreshClippingPlaneWorld()" in source
    assert "applyMatrix4(group.matrixWorld, clippingNormalMatrix)" in source
    assert "sourceBounds.min" in source and "sourceBounds.max" in source
    assert "function safeClippingPercent" in source
    assert "Math.max(numeric, 5)" in source and "Math.min(numeric, 95)" in source
    assert "api.refreshClippingPlaneWorld?.();" in xr


def test_reference_sync_restores_previous_manual_clipping_state():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")

    assert "referenceSyncPreviousClippingState = getClippingState();" in source
    assert "corte anterior restaurado" in source
    assert "clipEnabled.checked = previous.enabled" in source

    dimensions = server.StructureDimensions3DPayload(
        role="candidato",
        label="Região candidata",
        left_right_mm=18.2,
        anterior_posterior_mm=11.4,
        superior_inferior_mm=20.1,
    )
    assert dimensions.coordinate_system == "LPS"
    assert dimensions.approximate is True

    with pytest.raises(ValidationError):
        server.StructureDimensions3DPayload(
            role="candidato",
            label="Região candidata",
            left_right_mm=18.2,
            anterior_posterior_mm=0,
            superior_inferior_mm=20.1,
        )


def test_saved_views_support_local_ab_comparison_without_persisting_pixels():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "viewer" / "index.html").read_text(encoding="utf-8")

    assert 'id="saved-view-comparison"' in html
    assert "function toggleSavedViewComparison(bookmarkId)" in source
    assert "function renderSavedViewComparison()" in source
    assert 'snapshot_data_url: snapshotDataUrl' in source
    assert "renderer.domElement.toDataURL(\"image/png\")" in source
    assert "compared_saved_view_ids: comparedSavedViewIds.slice(0, 2)" in source
    payload_body = source.split("function savedViewPayload(view)", 1)[1].split(
        "function saveCurrentView", 1
    )[0]
    assert "snapshot_data_url" not in payload_body
    comparison_body = source.split("function renderSavedViewComparison()", 1)[1].split(
        "function renderSavedViews", 1
    )[0]
    assert "fetch(" not in comparison_body

    state = server.ViewerStatePayload(compared_saved_view_ids=[])
    assert state.compared_saved_view_ids == []

    with pytest.raises(ValidationError):
        server.ViewerStatePayload(compared_saved_view_ids=["a", "b", "c"])


def test_selected_3d_structure_moves_2d_reference_to_nearest_physical_plane():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")

    assert "function structureCenterLps(mesh)" in source
    assert "mesh.geometry.computeBoundingBox()" in source
    assert "function alignReferenceToStructure(item, mesh)" in source
    assert "centerLps[axis]" in source
    assert "frame.position_lps_mm" in source
    assert "Math.abs(candidate.position - coordinateLps)" in source
    assert "referenceSlider.value = String(nearest.index)" in source
    assert "renderReferenceFrame();" in source
    assert "referenceSync.checked && syncReferenceToClipping()" in source
    assert "alignReferenceToStructure(item, mesh);" in source
    alignment_body = source.split("function alignReferenceToStructure", 1)[1].split(
        "function selectReferenceView", 1
    )[0]
    assert "fetch(" not in alignment_body


def test_viewer_presents_mask_volumetry_quality_range_and_downloads():
    source = (ROOT / "viewer" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "viewer" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "viewer" / "argos-viewer.css").read_text(encoding="utf-8")

    assert 'id="volumetry-section"' in html
    assert "function renderVolumetry(manifest, fileMap, baseUrl" in source
    assert "payload?.whole_liver_summary" in source
    assert "technical_range_ml" in source
    assert "couinaud_partition" in source
    assert "selectStructure(item.role)" in source
    assert "Baixar JSON" in source and "Baixar CSV" in source
    assert ".volumetry-primary" in css
