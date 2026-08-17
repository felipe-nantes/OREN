import os, re, csv, json, collections, sys

BS = chr(92)
ROOT = r"C:\Users\profurg\Desktop\sander\argos-main\.claude\worktrees\fable-engineering-phase-00-b0172f"
OUT  = sys.argv[1]

EXCLUDE_DIRS = {".git", "graphify-out", ".claude", "__pycache__"}
TEXT_EXT = {".py",".ps1",".cmd",".sh",".bat",".yaml",".yml",".toml",".json",".md",".txt",".html",".js",".css",".cfg",".ini",".ipynb"}

def category(rel):
    top = rel.split("/")[0]
    if top == "tools": return "TOOLS"
    if top == "tests": return "TESTS"
    if top in ("dtwin","webapp","viewer") or rel == "digital_twin.py": return "RUNTIME"
    if top in ("docs","contexto") or (top.endswith(".md") and "/" not in rel): return "DOCS"
    if top in ("docker",".github","profiles","configs","benchmarks") or rel.startswith("compose") or rel.endswith((".cmd",".ps1",".sh")) or rel=="pyproject.toml": return "LAUNCH"
    return "OTHER"

corpus = {}
tool_files = []
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in EXCLUDE_DIRS]
    for fn in fns:
        full = os.path.join(dp, fn)
        rel = os.path.relpath(full, ROOT).replace(BS, "/")
        ext = os.path.splitext(fn)[1].lower()
        if rel.startswith("tools/"):
            tool_files.append(rel)
        if ext in TEXT_EXT:
            try:
                with open(full, encoding="utf-8", errors="ignore") as f:
                    corpus[rel] = f.read().replace(BS, "/")
            except OSError:
                pass

tool_files.sort()
print(f"tools files: {len(tool_files)}; corpus: {len(corpus)} arquivos texto", file=sys.stderr)

rows = []
for t in tool_files:
    base = t.rsplit("/",1)[1]
    relnp = t[len("tools/"):]
    fullref = "tools/" + relnp
    pat_base = re.compile(r"(?<![" + BS + "w.])" + re.escape(base) + r"(?![" + BS + "w])")
    modref = None
    if base.endswith(".py"):
        modref = "tools." + relnp[:-3].replace("/", ".")
    counts = collections.Counter(); strong = collections.Counter()
    for rel, text in corpus.items():
        if rel == t: continue
        cat = category(rel)
        n_full = text.count(fullref)
        n_imp  = text.count(modref) if modref else 0
        n_base = len(pat_base.findall(text))
        if n_full or n_imp:
            counts[cat] += max(n_full + n_imp, n_base); strong[cat] += n_full + n_imp
        elif n_base:
            counts[cat] += n_base
    def c(k): return counts.get(k,0)
    if c("RUNTIME")+c("LAUNCH")+c("OTHER") > 0: cls = "RUNTIME_OR_LAUNCH_WIRED"
    elif c("TESTS") > 0: cls = "TEST_REFERENCED_ONLY"
    elif c("TOOLS") > 0: cls = "TOOLCHAIN_ONLY"
    elif c("DOCS") > 0: cls = "DOC_REFERENCED_ONLY"
    else: cls = "STATIC_ORPHAN"
    conf = "STRONG" if sum(strong.values())>0 else ("WEAK" if sum(counts.values())>0 else "NONE")
    rows.append({"tool": t, "class": cls, "confidence": conf,
                 "runtime": c("RUNTIME"), "launch": c("LAUNCH"), "tests": c("TESTS"),
                 "tools": c("TOOLS"), "docs": c("DOCS"), "other": c("OTHER"),
                 "strong_total": sum(strong.values())})

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

summ = collections.Counter(r["class"] for r in rows)
conf = collections.Counter(r["confidence"] for r in rows)
print(json.dumps({"total": len(rows), "por_classe": dict(summ.most_common()), "confianca": dict(conf.most_common())}, ensure_ascii=False))
