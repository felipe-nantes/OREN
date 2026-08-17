# Status estático dos scripts de `tools/` — snapshot 9683eaa

Gerado em 2026-08-17 por TASK-2026-08-17-PH01-CARTO-02 (PHASE_01 wave 2). Método: referências cruzadas estáticas sobre 1.239 arquivos-texto do worktree congelado (caminho completo `tools/<x>`, import `tools.<x>` e basename com fronteira de palavra; corpus exclui .git/graphify-out; caminhos normalizados). **Nenhum script foi executado.**

Classes em escada de dominância (a mais forte vence): RUNTIME_OR_LAUNCH_WIRED > TEST_REFERENCED_ONLY > TOOLCHAIN_ONLY > DOC_REFERENCED_ONLY > STATIC_ORPHAN. Uma classe inferior pode ter refs adicionais de classes ainda mais baixas (ex.: TEST_REFERENCED_ONLY pode também aparecer em docs). Contagens por origem estão no CSV: `evidence/PH01/tools_status_9683eaa.csv` (script gerador ao lado).

**IMPORTANTE:** `tools/` são CLIs de operador/pesquisa; `STATIC_ORPHAN` significa *sem referência estática no repositório*, não “morto”. Remoção exige prova de reachability runtime + fase própria + autorização (LONG_PLAN item 10).

| Classe | n | Interpretação |
|---|---|---|
| RUNTIME_OR_LAUNCH_WIRED | 13 | referenciado por runtime (dtwin/webapp/viewer/digital_twin.py) ou por launchers/compose/CI/configs |
| TEST_REFERENCED_ONLY | 27 | sem refs de runtime/launch; referenciado por tests/ |
| TOOLCHAIN_ONLY | 23 | referenciado apenas por outros scripts de tools/ |
| DOC_REFERENCED_ONLY | 87 | referenciado apenas em docs/contexto/READMEs |
| STATIC_ORPHAN | 157 | nenhuma referência estática encontrada |
| **total** | **307** | |

## RUNTIME_OR_LAUNCH_WIRED (13)

| Script | runtime | launch | tests |
|---|---|---|---|
| `tools/create_quest_certificate.py` | 0 | 1 | 1 |
| `tools/evaluate_openswisshcc_v23_shape_fusion.py` | 0 | 1 | 0 |
| `tools/freeze_openswisshcc_v23_shape_calibrator.py` | 0 | 1 | 0 |
| `tools/graphify_argos.ps1` | 0 | 1 | 2 |
| `tools/infer_openswisshcc_case.py` | 1 | 0 | 0 |
| `tools/lld_mmri_v23_segment_worker.py` | 1 | 0 | 0 |
| `tools/medgemma_server.py` | 0 | 4 | 4 |
| `tools/quest_network.ps1` | 0 | 3 | 1 |
| `tools/serve_quest_certificate.py` | 0 | 1 | 3 |
| `tools/setup_medgemma.py` | 0 | 3 | 0 |
| `tools/start_oren_quest_dynamic.ps1` | 0 | 1 | 2 |
| `tools/train_medsiglip_multiclass.py` | 1 | 0 | 0 |
| `tools/verify_medsiglip_device_agreement.py` | 1 | 3 | 0 |

## TEST_REFERENCED_ONLY (27)

- `tools/build_anatomic_material_textures.py`
- `tools/build_lld_mmri_v23_roi_ceiling_t2dwi_embedding_pilot.py`
- `tools/build_openswisshcc_candidates.py`
- `tools/build_rag_corpus.py`
- `tools/build_rag_index.py`
- `tools/create_quest_access_page.py`
- `tools/download_http_ranges.py`
- `tools/ensure_docker_desktop.ps1`
- `tools/ensure_quest_firewall.ps1`
- `tools/eval_rag_retrieval.py`
- `tools/export_argos_portable.ps1`
- `tools/import_argos_portable.sh`
- `tools/initialize_argos_docker.sh`
- `tools/make_synthetic_case.py`
- `tools/medgemma_server_v14.py`
- `tools/score_medsiglip_panel.py`
- `tools/setup_graphify_argos.ps1`
- `tools/smoke_test_argos_docker_e2e.py`
- `tools/start_argos_docker.ps1`
- `tools/start_medgemma.ps1`
- `tools/start_medgemma_gateway_win.ps1`
- `tools/stop_argos_docker.ps1`
- `tools/stop_medgemma_gateway_win.ps1`
- `tools/verify_argos_docker_job.py`
- `tools/verify_argos_docker_static.py`
- `tools/verify_graphify_argos.py`
- `tools/verify_medgemma_container.ps1`

## TOOLCHAIN_ONLY (23)

- `tools/align_openswisshcc.py`
- `tools/bootstrap_argos_mac.sh`
- `tools/build_production_liver_masks_for_selection.py`
- `tools/initialize_argos_docker.ps1`
- `tools/liver_segments_mr_worker.py`
- `tools/measure_four_phase_union_gain.py`
- `tools/measure_liver_segments_mr_vs_chaos_reference.py`
- `tools/measure_total_mr_vs_chaos_reference.py`
- `tools/medgemma_server_base.py`
- `tools/render_best_worst_gallery.py`
- `tools/render_openswisshcc_candidate.py`
- `tools/run_openswisshcc_holdout_v21.py`
- `tools/run_openswisshcc_holdout_v21_isolated_localizer.py`
- `tools/run_openswisshcc_lesion_localizer_chunk.py`
- `tools/run_openswisshcc_lesion_localizer_pilot.py`
- `tools/run_openswisshcc_volumetric_pairwise.py`
- `tools/setup_docker_windows.ps1`
- `tools/single_label_segment_worker.py`
- `tools/smoke_gpu.py`
- `tools/start_argos_docker_mac.sh`
- `tools/test_vessel_closing_gate.py`
- `tools/verify_argos_docker_portable.sh`
- `tools/vessel_continuity_segment_worker.py`

## DOC_REFERENCED_ONLY (87)

`__init__.py`, `adjudicate_hcc_benign_mimic.py`, `audit_liver_mask_geometry_quality.py`, `audit_liver_mri_dataset.py`, `audit_lld_mmri_v23_geometry.py`, `audit_mesh_topology_quality.py`, `audit_openswisshcc_axial_atlas_v17.py`, `build_liver_candidate_dataset.py`, `build_lld_mmri_v23_enhancement_panels.py`, `build_lld_mmri_v23_panels.py`, `build_openswisshcc_axial_atlas_v17.py`, `build_openswisshcc_fusion_v11.py`, `build_openswisshcc_review_gallery.py`, `build_openswisshcc_v15_blind_fusion.py`, `build_patch25d_dataset.py`, `build_public_independent_cohort_v21.py`, `build_raw_phase_review_gallery.py`, `build_synthetic_external_stress_v1.py`, `check_hybrid_training_environment.py`, `download_chaos_v103.py`, `download_lld_mmri_v23_external.py`, `evaluate_hybrid_robustness.py`, `evaluate_late_fusion.py`, `evaluate_liverhccseg_v21_positive.py`, `evaluate_openswisshcc_fusion_v11.py`, `evaluate_openswisshcc_holdout_v21.py`, `evaluate_openswisshcc_run.py`, `evaluate_openswisshcc_v15_fusion.py`, `evaluate_synthetic_external_stress_v1.py`, `extract_candidate_radiomics.py`, `extract_chaos_mri_v103.py`, `extract_medsiglip_embeddings.py`, `filter_liverhccseg_tumor_positive.py`, `freeze_hybrid_training_protocol.py`, `freeze_lld_mmri_v23_technical_amendment.py`, `freeze_openswisshcc_candidate_volume_score_v16.py`, `freeze_openswisshcc_experiment.py`, `freeze_openswisshcc_fusion_v11.py`, `freeze_openswisshcc_v15_fusion.py`, `harmonize_lld_mmri_v23_dynamic_t1.py`, `measure_deployed_subtype_accuracy.py`, `measure_liver_segments_mr_vs_total_mr_venous_lld.py`, `measure_three_phase_union_gain.py`, `pilot_lld_mmri_v23_segmentation.py`, `pilot_precontrast_liver_segmentation.py`, `prepare_gd_eob_hcc_external.py`, `prepare_liverhccseg_v21.py`, `prepare_lld_mmri_v23_external.py`, `prepare_v23_external_validation.py`, `prepare_v23_retrospective_multicohort.py`, `prepare_v23_retrospective_multicohort_phase2.py`, `prepare_v23_retrospective_multicohort_phase3.py`, `remediate_openswisshcc_candidates.py`, `render_spotlight_panel.py`, `review_liverhccseg_v21_panels.py`, `review_lld_mmri_v23.py`, `review_openswisshcc_candidate_volume_v16.py`, `review_openswisshcc_holdout_v21.py`, `review_openswisshcc_multisequence.py`, `review_openswisshcc_panels.py`, `run_internal_blind_visual_case.py`, `run_liverhccseg_v21_signals.py`, `run_mrsegmentator_chaos_gpu_v2.py`, `run_openswisshcc_axial_atlas_score_v17.py`, `run_openswisshcc_candidate_volume_score_v16.py`, `run_openswisshcc_inference.py`, `run_openswisshcc_lesion_localizer_pilot_win.ps1`, `run_raw_phase_equivalence_benchmark.py`, `run_segmentation_visualization_shadow_v2.py`, `run_visual_benchmark.py`, `setup_real_env.py`, `stop_medgemma.ps1`, `test_morphological_closing_gate.py`, `test_mrsegmentator_isolated.py`, `train_medsiglip_classifier.py`, `train_medsiglip_head.py`, `train_medsiglip_partial.py`, `train_patch25d_classifier.py`, `train_radiomics_classifier.py`, `validate_phase_union_against_reference.py`, `verify_argos_docker_runtime.ps1`, `verify_lld_mmri_v23_segmentation_audit.py`, `verify_medsiglip_phase13.py`, `verify_openswisshcc_v23_baseline.py`, `verify_synthetic_external_stress_v1.py`, `verify_synthetic_external_stress_v1_evaluation.py`, `verify_volumetry.py`

## STATIC_ORPHAN (157)

`align_openswisshcc_holdout.py`, `analyze_medsiglip_external_recalibration.py`, `analyze_openswisshcc_v11_v13_complementarity.py`, `analyze_openswisshcc_volumetric_fusion.py`, `assemble_best_worst_case_folders.py`, `audit_monophase_external_failures.py`, `audit_openswisshcc_arterial_union_pilot_v22.py`, `audit_openswisshcc_candidate_localization_v16.py`, `audit_openswisshcc_enhancement_localizer_v22.py`, `audit_openswisshcc_holdout_blind.py`, `audit_openswisshcc_multisequence.py`, `audit_openswisshcc_v23_errors.py`, `benchmark_liver_segmentation_v2.py`, `build_chaos_v21_panels.py`, `build_dicom_quality_showcase.py`, `build_internal_blind_benchmark_120.py`, `build_liverhccseg_v21_panels.py`, `build_lld_mmri_v23_full_fov_pilot.py`, `build_lld_mmri_v23_liver_enriched_pilot.py`, `build_lld_mmri_v23_shape.py`, `build_localized_candidate_features.py`, `build_localized_candidate_supervision.py`, `build_medsiglip_monophase_dataset.py`, `build_monophase_complementary_candidates.py`, `build_monophase_slice_candidates.py`, `build_openswiss_monophase_atlas_candidates.py`, `build_openswisshcc_candidate_enhancement_v22.py`, `build_openswisshcc_candidate_shape_v23.py`, `build_openswisshcc_candidate_volume_fallback_v16.py`, `build_openswisshcc_candidate_volume_full87_v16.py`, `build_openswisshcc_candidate_volume_timing_v16.py`, `build_openswisshcc_candidate_volume_v16.py`, `build_openswisshcc_enhancement_features_v22.py`, `build_openswisshcc_enhancement_localizer_v22.py`, `build_openswisshcc_highdimensional_stack.py`, `build_openswisshcc_holdout_panels.py`, `build_openswisshcc_localizer_enhancement_roi_pilot.py`, `build_openswisshcc_localizer_roi_pilot.py`, `build_openswisshcc_multisequence_cohort.py`, `build_openswisshcc_multisequence_gallery.py`, `build_openswisshcc_multisequence_quality_bundle.py`, `build_openswisshcc_volumetric_candidates.py`, `build_openswisshcc_volumetric_gallery.py`, `build_relatorio_consolidado_docx.js`, `combine_final_liver_vessel_score.py`, `consolidate_public_independent_v21.py`, `diagnose_external_signals.py`, `diagnose_lld_mmri_v23_liver_fallback.py`, `evaluate_chaos_v21_negative.py`, `evaluate_lld_mmri_v23_external.py`, `evaluate_lld_mmri_v23_liver_enriched.py`, `evaluate_medsiglip_external_bundle.py`, `evaluate_multi_signal_fusion.py`, `evaluate_openswisshcc_axial_atlas_chunk_v18.py`, `evaluate_openswisshcc_axial_atlas_rag_v19.py`, `evaluate_openswisshcc_axial_atlas_v17.py`, `evaluate_openswisshcc_candidate_volume_v16.py`, `evaluate_openswisshcc_enhancement_features_v22.py`, `evaluate_openswisshcc_enhancement_pilot_v22.py`, `evaluate_openswisshcc_highdimensional_v13.py`, `evaluate_openswisshcc_lesion_localizer_full87_v10.py`, `evaluate_openswisshcc_localizer_roi_v10.py`, `evaluate_openswisshcc_multisequence.py`, `evaluate_openswisshcc_slice_pairwise.py`, `evaluate_openswisshcc_v24_planarity_contrast.py`, `evaluate_openswisshcc_v25_sphericity.py`, `evaluate_openswisshcc_v26_bbox_fill.py`, `evaluate_openswisshcc_v27_nested_recalibration.py`, `evaluate_openswisshcc_volumetric_pairwise.py`, `evaluate_openswisshcc_volumetric_run.py`, `evaluate_v24_liver_enriched.py`, `extract_openswisshcc_holdout_transforms.py`, `extract_openswisshcc_transforms.py`, `filter_monophase_complementary_embeddings.py`, `finalize_openswisshcc_candidate_variant.py`, `freeze_chaos_v21_evaluation_protocol.py`, `freeze_liverhccseg_v21_evaluation_protocol.py`, `freeze_lld_mmri_v23_external_protocol.py`, `freeze_lld_mmri_v23_predictions.py`, `freeze_openswisshcc_candidate_volume_evaluation_v16.py`, `freeze_openswisshcc_enhancement_pilot_evaluation_v22.py`, `freeze_openswisshcc_highdimensional_batch.py`, `freeze_openswisshcc_highdimensional_pilot.py`, `freeze_openswisshcc_lesion_localizer_evaluation_v10.py`, `freeze_openswisshcc_localizer_roi_v10.py`, `freeze_openswisshcc_multisequence.py`, `freeze_openswisshcc_volume_score_v14.py`, `freeze_openswisshcc_volumetric.py`, `freeze_public_independent_calibrator_v21.py`, `freeze_segmentation_visualization_baseline.py`, `fuse_liver_masks_registered_phases_v2.py`, `infer_openswisshcc_volumetric_case.py`, `measure_vessel_continuity_shortlist.py`, `merge_openswisshcc_lesion_localizer_chunks.py`, `merge_openswisshcc_multisequence_chunks.py`, `pilot_monophase_subtype_adjudication.py`, `plan_openswisshcc_candidate_volume_timing_v16.py`, `plan_openswisshcc_multisequence_chunks.py`, `preflight_openswisshcc_enhancement_top5_v22.py`, `prepare_chaos_v21.py`, `prepare_openswisshcc.py`, `prepare_openswisshcc_highdimensional_batch.py`, `prepare_openswisshcc_holdout_blind.py`, `prepare_v24_liver_enriched_openswisshcc.py`, `profile_openswisshcc_localizer_roi_v10_timing.py`, `project_openswisshcc_enhancement_top5_timing_v22.py`, `rank_liver_integrity_candidates.py`, `rebind_medsiglip_embeddings.py`, `render_liver_mesh_gallery.py`, `render_liver_state_gallery.py`, `render_liver_union_gallery.py`, `render_openswisshcc_fallback.py`, `render_openswisshcc_multisequence.py`, `render_segmentation_shadow_mesh_comparison_v2.py`, `report_openswisshcc_v11_v13_cross_tab.py`, `review_chaos_v21_panels.py`, `review_lld_mmri_v23_full_fov.py`, `review_lld_mmri_v23_liver_enriched.py`, `review_openswisshcc_axial_atlas_v17.py`, `review_openswisshcc_localizer_roi_v10.py`, `review_openswisshcc_multisequence_quality.py`, `review_openswisshcc_volumetric.py`, `run_chaos_v21_signals.py`, `run_gd_eob_hbp_pilot.py`, `run_lld_mmri_v23_full_fov_timing.py`, `run_lld_mmri_v23_liver_enriched_timing.py`, `run_lld_mmri_v23_signals.py`, `run_multi_signal_production.py`, `run_openswisshcc_arterial_union_localizer_v22.py`, `run_openswisshcc_axial_atlas_chunk_v18.py`, `run_openswisshcc_axial_atlas_rag_v19.py`, `run_openswisshcc_candidate_volume_timing_v16.py`, `run_openswisshcc_highdimensional_batch.py`, `run_openswisshcc_highdimensional_pilot.py`, `run_openswisshcc_holdout_v21_localizer_win.ps1`, `run_openswisshcc_holdout_v21_medsiglip_win.ps1`, `run_openswisshcc_lesion_localizer_chunk_win.ps1`, `run_openswisshcc_localizer_roi_v10_ab.py`, `run_openswisshcc_multisequence_chunk.py`, `run_openswisshcc_multisequence_pairwise.py`, `run_openswisshcc_slice_pairwise.py`, `run_openswisshcc_v20_fusion.py`, `run_openswisshcc_volume_score_batch_v14.py`, `run_openswisshcc_volume_score_pilot_v14.py`, `run_openswisshcc_volumetric_inference.py`, `run_openswisshcc_volumetric_medsiglip.py`, `run_totalsegmentator_liver_cohort_v2.py`, `run_v23_retrospective_multicohort_phase4.py`, `run_v24_liver_enriched_inference.py`, `scan_openswisshcc_multisequence_geometry.py`, `segment_aorta_for_gallery.py`, `select_openswisshcc_enhancement_proposals_v22.py`, `smoke_monophase_advisory.py`, `start_oren_webapp_only.ps1`, `time_openswisshcc_candidate_shape_v23.py`, `train_medsiglip_pairwise_subtype.py`, `verify_internal_blind_benchmark_120.py`

## Limitações do método

- Invocação dinâmica por string construída (f-string/concatenação) não é detectada; verificação por amostragem não encontrou `subprocess/importlib` apontando para tools no runtime.
- Referências em notebooks fora do repo, shells de operador ou histórico git não contam.
- 3 classificações têm confiança WEAK (apenas basename); ver coluna `confidence` no CSV.
