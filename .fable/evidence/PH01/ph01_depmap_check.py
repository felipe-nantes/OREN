import os, re, sys, glob

ROOT = r"C:\Users\profurg\Desktop\sander\argos-main\.claude\worktrees\fable-engineering-phase-00-b0172f"
PACK = r"C:\Users\profurg\Desktop\sander\argos-main\.fable"

def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore") as f:
        return f.read()

# (edge_label, importer_file, regex_pattern)
EDGES = [
 ("digital_twin -> dtwin(Engine)", "digital_twin.py", r"from dtwin import .*Engine|from dtwin\.engine import"),
 ("dtwin/__init__ exporta Engine", "dtwin/__init__.py", r"engine|Engine"),
 ("engine -> stages", "dtwin/engine.py", r"from \. import stages|from \.stages import"),
 ("stages -> core", "dtwin/stages.py", r"from \.core import|from \. import core"),
 ("stages -> segmentation_contract", "dtwin/stages.py", r"segmentation_contract"),
 ("stages -> volumetry", "dtwin/stages.py", r"from \.volumetry import"),
 ("stages -> viewer_artifacts", "dtwin/stages.py", r"from \.viewer_artifacts import"),
 ("stages -> viewer_xr", "dtwin/stages.py", r"viewer_xr"),
 ("server -> raw_dicom_phase_resolver", "webapp/server.py", r"raw_dicom_phase_resolver"),
 ("server -> multiphase_ingest", "webapp/server.py", r"multiphase_ingest"),
 ("server -> segmentation_subprocess", "webapp/server.py", r"segmentation_subprocess"),
 ("server -> segmentation_shadow", "webapp/server.py", r"segmentation_shadow"),
 ("server -> learning visual/classifier", "webapp/server.py", r"visual_inference|medsiglip"),
 ("server -> benchmark metrics/reporting", "webapp/server.py", r"from dtwin\.benchmark|dtwin\.benchmark\."),
 ("server -> candidate_subprocess", "webapp/server.py", r"candidate_subprocess"),
 ("core -> SimpleITK/yaml/numpy", "dtwin/core.py", r"import SimpleITK|import yaml|import numpy"),
 ("resolver -> pydicom", "dtwin/learning/raw_dicom_phase_resolver.py", r"pydicom"),
 ("multiphase_ingest -> pydicom+SimpleITK", "dtwin/learning/multiphase_ingest.py", r"pydicom|SimpleITK"),
 ("classifiers -> medsiglip_embeddings", "dtwin/learning/medsiglip_classifier.py", r"medsiglip_embeddings"),
 ("multiclass -> medsiglip_embeddings", "dtwin/learning/medsiglip_multiclass_classifier.py", r"medsiglip_embeddings"),
]

print("== DEPENDENCY_MAP: edges estáticos ==")
fail = 0
for label, rel, pat in EDGES:
    try:
        text = read(rel)
        ok = re.search(pat, text) is not None
    except OSError:
        ok = None
    if ok is True: status = "VERIFIED"
    elif ok is None: status = "FILE_MISSING"; fail += 1
    else: status = "NOT_FOUND"; fail += 1
    print(f"  [{status}] {label}")

print()
print("== MODULE CARDS: existência dos paths citados ==")
pat_path = re.compile(r"`((?:dtwin|webapp|viewer|tools|configs|profiles|docs|tests|docker|benchmarks)/[\w./\-]+|digital_twin\.py|pyproject\.toml|compose[\w.]*\.yaml|run_[\w.]+|INICIAR_[\w.]+|[A-Z_]+\.cmd)`")
total_missing = []
for card in sorted(glob.glob(os.path.join(PACK, "modules", "*.md"))):
    name = os.path.basename(card)
    if name == "INDEX.md": continue
    text = open(card, encoding="utf-8").read()
    paths = sorted(set(pat_path.findall(text)))
    missing = [p for p in paths if not os.path.exists(os.path.join(ROOT, p))]
    tag = "OK" if not missing else "MISSING"
    print(f"  [{tag}] {name}: {len(paths)} paths citados" + (f"; ausentes: {missing}" if missing else ""))
    total_missing += [(name, m) for m in missing]

print()
print(f"RESUMO: edges_falhos={fail}; paths_ausentes={len(total_missing)}")
