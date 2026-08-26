# -*- coding: utf-8 -*-
"""REF-06B: indice de status dos tools/ na arvore ATUAL (metodologia PH01).

Reusa a escada de dominancia da PHASE_01 (RUNTIME_OR_LAUNCH_WIRED >
TEST_REFERENCED_ONLY > TOOLCHAIN_ONLY > DOC_REFERENCED_ONLY > STATIC_ORPHAN)
sobre o checkout atual, e emite tools/TOOLS_STATUS_INDEX.yaml + CSV evidencia.
"""
import collections
import csv
import os
import re
import sys

import yaml

BS = chr(92)
ROOT = r"C:\Users\profurg\Desktop\sander\argos-main"
EXCLUDE_DIRS = {".git", "graphify-out", ".claude", "__pycache__", ".venv", ".venv-win",
                ".venv-mrseg", ".codex-tmp", ".tmp-medgemma-official", ".local",
                ".mypy_cache", ".ruff_cache", ".pytest_cache", ".hypothesis",
                "casos", "data", "flywheel", "artifacts", "experiments"}
TEXT_EXT = {".py", ".ps1", ".cmd", ".sh", ".bat", ".yaml", ".yml", ".toml", ".json",
            ".md", ".txt", ".html", ".js", ".css", ".cfg", ".ini", ".ipynb"}


def category(rel):
    top = rel.split("/")[0]
    if top == "tools":
        return "TOOLS"
    if top == "tests":
        return "TESTS"
    if top in ("dtwin", "webapp", "viewer") or rel == "digital_twin.py":
        return "RUNTIME"
    if top in ("docs", "contexto") or (top.endswith(".md") and "/" not in rel):
        return "DOCS"
    if (top in ("docker", ".github", "profiles", "configs", "benchmarks", "locks")
            or rel.startswith("compose") or rel.endswith((".cmd", ".ps1", ".sh"))
            or rel == "pyproject.toml"):
        return "LAUNCH"
    return "OTHER"


# Corpus = SOMENTE arquivos git-tracked (replica honesta da PH01, cujo
# worktree congelado era um checkout limpo; o checkout vivo tem rag/corpus e
# outros nao-versionados cheios de texto que citam basenames e poluiriam tudo).
import subprocess
tracked = subprocess.run(
    ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
).stdout.splitlines()
corpus = {}
tool_files = []
# Inventarios/registros NAO sao consumo: listar um tool num indice, no pack
# de auditoria ou no mapa do graphify nao o torna "wired". Sem esta exclusao
# TUDO vira RUNTIME_OR_LAUNCH_WIRED (o proprio TOOLS_STATUS.md da PH01 lista
# os 307). PH01 nao sofria disso porque esses arquivos ainda nao existiam.
INVENTARIOS = (".fable/", "graphify-out/", "configs/CONFIG_STATUS_INDEX.yaml",
               "tools/TOOLS_STATUS_INDEX.yaml")
tracked = [r for r in tracked if not r.startswith(INVENTARIOS)]
for rel in tracked:
    ext = os.path.splitext(rel)[1].lower()
    if rel.startswith("tools/") and rel != "tools/TOOLS_STATUS_INDEX.yaml":
        tool_files.append(rel)
    if ext in TEXT_EXT:
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore") as f:
                corpus[rel] = f.read().replace(BS, "/")
        except OSError:
            pass

tool_files.sort()
print(f"tools: {len(tool_files)}; corpus: {len(corpus)}", file=sys.stderr)

rows = []
for t in tool_files:
    base = t.rsplit("/", 1)[1]
    relnp = t[len("tools/"):]
    fullref = "tools/" + relnp
    pat_base = re.compile(r"(?<![" + BS + "w.])" + re.escape(base) + r"(?![" + BS + "w])")
    modref = "tools." + relnp[:-3].replace("/", ".") if base.endswith(".py") else None
    counts = collections.Counter()
    strong = collections.Counter()
    for rel, text in corpus.items():
        if rel == t or rel == "tools/TOOLS_STATUS_INDEX.yaml":
            continue
        cat = category(rel)
        n_full = text.count(fullref)
        n_imp = text.count(modref) if modref else 0
        n_base = len(pat_base.findall(text))
        if n_full or n_imp:
            counts[cat] += max(n_full + n_imp, n_base)
            strong[cat] += n_full + n_imp
        elif n_base:
            counts[cat] += n_base

    def c(k):
        return counts.get(k, 0)

    if c("RUNTIME") + c("LAUNCH") + c("OTHER") > 0:
        cls = "RUNTIME_OR_LAUNCH_WIRED"
    elif c("TESTS") > 0:
        cls = "TEST_REFERENCED_ONLY"
    elif c("TOOLS") > 0:
        cls = "TOOLCHAIN_ONLY"
    elif c("DOCS") > 0:
        cls = "DOC_REFERENCED_ONLY"
    else:
        cls = "STATIC_ORPHAN"
    conf = "STRONG" if sum(strong.values()) > 0 else ("WEAK" if sum(counts.values()) > 0 else "NONE")
    rows.append({"tool": t, "class": cls, "confidence": conf,
                 "runtime": c("RUNTIME"), "launch": c("LAUNCH"), "tests": c("TESTS"),
                 "tools": c("TOOLS"), "docs": c("DOCS"), "other": c("OTHER"),
                 "strong_total": sum(strong.values())})

csv_path = os.path.join(ROOT, ".fable", "post_audit", "evidence", "REF-06B", "tools_status_atual.csv")
os.makedirs(os.path.dirname(csv_path), exist_ok=True)
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

summ = collections.Counter(r["class"] for r in rows)
saida = {
    "schema": "argos-tools-status-index-v1",
    "task": "TASK-2026-08-25-REF-06B (W-046/TD-003)",
    "generated": "2026-08-25",
    "metodo": (
        "Escada de dominancia da PHASE_01 re-executada sobre o checkout ATUAL "
        "(pos-decomposicao REF-03): RUNTIME_OR_LAUNCH_WIRED > "
        "TEST_REFERENCED_ONLY > TOOLCHAIN_ONLY > DOC_REFERENCED_ONLY > "
        "STATIC_ORPHAN. Referencias estaticas (caminho completo, import "
        "tools.<x>, basename com fronteira); NENHUM script executado. "
        "Corpus = git-tracked MENOS inventarios (.fable/, graphify-out/, os proprios indices): registro nao e consumo. Gerador: evidence/REF-06B/."
    ),
    "aviso": (
        "tools/ sao CLIs de operador/pesquisa; STATIC_ORPHAN = sem referencia "
        "estatica, NAO 'morto'. Remocao exige prova de reachability runtime + "
        "fase propria + autorizacao (LONG_PLAN item 10). Status e metadado "
        "consultivo de navegacao."
    ),
    "resumo": {"total": len(rows), **{k: v for k, v in sorted(summ.items())}},
    "tools": [
        {"path": r["tool"], "status": r["class"], "confidence": r["confidence"],
         "refs": {k: r[k] for k in ("runtime", "launch", "tests", "tools", "docs", "other") if r[k]}}
        for r in rows
    ],
}
idx_path = os.path.join(ROOT, "tools", "TOOLS_STATUS_INDEX.yaml")
with open(idx_path, "w", encoding="utf-8") as f:
    yaml.safe_dump(saida, f, allow_unicode=True, sort_keys=False, width=100)
yaml.safe_load(open(idx_path, encoding="utf-8"))
print(f"resumo: {dict(summ.most_common())}")
print(f"salvos: {idx_path} + {csv_path}")
