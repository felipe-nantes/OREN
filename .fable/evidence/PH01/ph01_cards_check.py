import os, re, glob

ROOT = r"C:\Users\profurg\Desktop\sander\argos-main\.claude\worktrees\fable-engineering-phase-00-b0172f"
PACK = r"C:\Users\profurg\Desktop\sander\argos-main\.fable"

pat = re.compile(r"(?:dtwin|webapp|viewer|tools|configs|profiles|tests|docker|benchmarks|docs)/[\w./\-]+|digital_twin\.py|pyproject\.toml|compose(?:\.portable)?\.yaml")
total_missing = []
total_paths = 0
for card in sorted(glob.glob(os.path.join(PACK, "modules", "*.md"))):
    name = os.path.basename(card)
    if name == "INDEX.md": continue
    text = open(card, encoding="utf-8").read()
    paths = sorted(set(p.rstrip(".,;") for p in pat.findall(text)))
    # ignora refs ao próprio pack e placeholders com wildcard
    paths = [p for p in paths if "*" not in p and not p.startswith(".fable")]
    missing = [p for p in paths if not os.path.exists(os.path.join(ROOT, p))]
    total_paths += len(paths)
    if missing:
        print(f"  [MISSING] {name}: {missing}")
        total_missing += [(name, m) for m in missing]
    else:
        print(f"  [OK] {name}: {len(paths)} paths")
print(f"RESUMO: cards=24, paths_verificados={total_paths}, ausentes={len(total_missing)}")
