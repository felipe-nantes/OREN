# Synthetic external multiphase stress cohort v1

Updated: 2026-07-31.

## Outcome

A 330-case synthetic, three-phase liver MRI cohort was materialized at:

`C:\Users\profurg\Desktop\sander\argos-main\data\generated\synthetic_external_stress_v1_330`

It contains exactly:

| Construction label | Cases |
|---|---:|
| No focal lesion | 100 |
| FNH | 50 |
| HCC | 60 |
| Simple cyst | 60 |
| Hemangioma | 60 |
| **Total** | **330** |

Every case has arterial, portal venous and delayed NIfTI volumes, a liver mask
for each phase, a construction lesion mask for each phase, file hashes and
explicit background/donor dependency groups.

This is a **synthetic technical stress cohort**, not a retrospective clinical
cohort. It cannot estimate clinical specificity, cannot support external
validation claims and is not allowed for clinical use.

## Sources

- Background anatomy and real dynamic acquisitions: 195 patients from the
  [NIH Clinical Center MRISegmenter dataset](https://github.com/rsummers11/MRISegmenter).
  The associated [Radiology paper](https://doi.org/10.1148/radiol.241979)
  documents precontrast, arterial, portal venous and delayed T1 volumes for all
  195 patients. The public dataset does not provide focal-lesion diagnoses.
- Lesion size and phase-specific enhancement signatures: public
  [LLD-MMRI-MedSAM2](https://huggingface.co/datasets/wanglab/LLD-MMRI-MedSAM2)
  images and voxel masks, pinned to revision
  `b7e8da56b267587689d8440e8298205f3fc4914e`. Exact public class counts were
  independently parsed from `LLD_MMRI_Annotation.json`: 46 FNH, 157 HCC,
  53 cysts and 79 hemangiomas.

Pinned source integrity:

- NIH ZIP: 4,806,567,799 bytes; SHA-256
  `debc5a832159e327ec8905af4674736ee8449a6608bec75380c7718a57d638b5`.
- LLD annotation JSON: 18,957,961 bytes; SHA-256
  `1b2737b82009d23321b39c23bb842d56de79bb7735bbbe3c61fd828300a26d2a`.

No email, form, registration or access request was sent. Both sources were
downloaded from their public endpoints.

## Construction

The frozen plan uses all 195 NIH patients as backgrounds, at most twice each.
It uses 219 unique LLD lesion donors, at most twice each. The dependency ids are
retained so synthetic outputs that reuse anatomy or a lesion donor must never be
treated as statistically independent patients.

For each background, low-frequency focal liver signal is removed while real
high-frequency scanner texture is retained. Positive cases then receive an
irregular lesion whose physical size, texture ratio and lesion-to-parenchyma
contrast in each phase are measured from an LLD donor. Phase-specific NIH liver
masks and their centroid displacement preserve respiratory motion between
arterial, venous and delayed acquisitions.

The implementation is in:

- `dtwin/benchmark/synthetic_external_stress_v1.py`
- `dtwin/benchmark/synthetic_external_stress_v1_eval.py`
- `tools/build_synthetic_external_stress_v1.py`
- `tools/verify_synthetic_external_stress_v1.py`
- `tools/evaluate_synthetic_external_stress_v1.py`
- `tools/verify_synthetic_external_stress_v1_evaluation.py`
- `tests/test_synthetic_external_stress_v1.py`
- `tests/test_synthetic_external_stress_v1_eval.py`

## Integrity and QA

The independent verifier reread every generated image and mask and recomputed
all hashes.

- Cohort signature:
  `9e8b81a6e40f51e8e2668ba753ead59da51c5ad59a517552b46d9d9c0e704c10`
- Cases JSONL SHA-256:
  `490d77a325c191b0470c05e8a7ac41840e01f7b8cb83f2c140f7828defffcddc`
- Verification signature:
  `9970c28d669817f4cc3e28ed39abd5950788b1ea4ed168fb0fca272901b783bc`
- Files: 3,307
- Size: 5.546 GiB
- Hashes verified: yes
- Identical phase grid within every case: yes
- Lesion inside the phase-specific liver mask: yes
- Empty lesion mask in every construction-negative case: yes

Construction QA shows broad physical-size variation rather than a fixed lesion:
median arterial lesion volumes were 12.76 mL for FNH, 27.52 mL for HCC,
4.45 mL for hemangioma and 1.90 mL for simple cyst. Median output
lesion-to-parenchyma contrast followed the intended broad patterns: FNH was
strongest in the arterial phase, cysts were hypointense in all phases and
hemangiomas showed higher median contrast in venous/delayed than arterial.
These are construction checks, not evidence of diagnostic realism.

Primary artifacts:

- `cohort_manifest.json`: counts, claim guards and cohort signature
- `cases.jsonl`: case-level paths, hashes and dependency groups
- `verification.json`: independent integrity result
- `qa_metrics.json`: construction-only volume and contrast distributions
- `qa_median_cases_montage.png`: representative visual QA

## Frozen-classifier technical stress result

The signed Etapa C MedSigLIP production bundle was executed on all 330 cases
using the same three liver-enriched multiphase panels used in development.
There were no technical failures.  These are metrics against construction
labels only and are deliberately named so they cannot be mistaken for clinical
sensitivity or specificity.

| Technical metric | Result |
|---|---:|
| HCC sensitivity on construction labels | 56.67% (34/60) |
| Negative rejection on construction labels | 52.22% (141/270) |
| Binary balanced accuracy on construction labels | 54.44% |
| FNH top-1 recall on construction labels | 0/50 (0%) |
| Four-lesion-subtype balanced accuracy | 0% |
| Construction-negative top-1 `negative_unspecified` | 66/100 (66%) |
| Technical failures | 0/330 |

The subtype result is not a subtle miss.  Mean panel-probability argmax never
selected the correct named class for FNH, HCC, hemangioma or hepatic cyst.  It
predicted primarily `negative_unspecified` or `positive_unspecified`, the two
classes associated with OpenSwissHCC during development.  On NIH anatomy, even
LLD-derived lesion signatures were therefore overwhelmed by acquisition-domain
signal.  This is a technical stress confirmation of the already measured
cohort confounding, not an estimate of clinical performance.

Evaluation artifacts are under `etapa_c_evaluation_v1/`:

- `evaluation.json`: signed aggregate result; report signature
  `c7ca2ad9765fa6b86b02596e4c17179db49daa11ec5c561b1b3c28afff14e79c`
- `evaluation_verification.json`: independent verification of all 330 record
  signatures, uniqueness, checkpoint hash, aggregate metrics and claim guards;
  verification signature
  `792c8440aca2627fc54819f5ee099b905a376572ddd3efd8f711f8b2c9ad5883`
- `checkpoint_predictions.jsonl`: 330 signed per-case records; SHA-256
  `fe5c761800080dc96620f68dfa77a0afbc83ffaed4bd15942bcb4db0dfdc9822`
- `protocol.json`: frozen inputs and claim guards; protocol signature
  `970074cc842ccc131e1274a99bc00fea84fcfc9f8e2a57119a244c89728a23bd`
- `checkpoint_recovery.json`: signed audit of one interrupted concurrent run;
  174 duplicate records were byte-identical, zero conflicted, and the canonical
  checkpoint contains exactly 330 rows
- `panels/`: the three rendered inference panels for every case

The evaluator now holds an operating-system file lock for the entire run, so a
second process cannot write to the same checkpoint.  Fifteen focused tests pass.

## Reproduction

From the repository root, using the configured Windows environment:

```powershell
.venv-win\Scripts\python.exe tools\build_synthetic_external_stress_v1.py `
  --nih-root data\raw\MRISegmenter_NIH_2025\extracted\MRISegmenter_T1only_public_20Jun2025\Release `
  --lld-root data\raw\LLD_MMRI_v23_hf `
  --output data\generated\synthetic_external_stress_v1_330 `
  --skip-download

.venv-win\Scripts\python.exe tools\verify_synthetic_external_stress_v1.py `
  --cohort data\generated\synthetic_external_stress_v1_330

.venv-win\Scripts\python.exe -m tools.evaluate_synthetic_external_stress_v1 `
  --cohort data\generated\synthetic_external_stress_v1_330 `
  --out data\generated\synthetic_external_stress_v1_330\etapa_c_evaluation_v1

.venv-win\Scripts\python.exe -m tools.verify_synthetic_external_stress_v1_evaluation `
  --evaluation data\generated\synthetic_external_stress_v1_330\etapa_c_evaluation_v1
```

Use `--resume` only with the same frozen `plan.json`. Existing cases are reused
only when their plan signature and synthesis algorithm id match.

## Claim boundary

Allowed:

- end-to-end pipeline smoke testing;
- robustness testing against a new acquisition background;
- checking phase ingestion, geometry harmonization and failure modes;
- exploratory comparison of model responses across constructed phenotypes.

Forbidden:

- calling the set retrospective patient data;
- reporting sensitivity, specificity, confidence intervals or prevalence as
  clinical estimates;
- claiming independent disease generalization, because lesion signatures come
  from LLD-MMRI, an already used source;
- claiming external clinical validation or publication-grade validation;
- using the set for clinical decisions.

The original mission remains open: a real, independently diagnosed cohort from
a new service is still required to establish false-positive rate, FNH
generalization and publication-grade external validation.
