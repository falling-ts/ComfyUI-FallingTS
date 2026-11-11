
import json, urllib.request, os, glob, re

WHITELIST = {
    "Note","MarkdownNote","Reroute","PrimitiveNode","PrimitiveInt","PrimitiveFloat",
    "PrimitiveString","PrimitiveBoolean","Note (hidden)",
}
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

oi = json.load(urllib.request.urlopen("http://127.0.0.1:8188/object_info", timeout=120))
registered = set(oi.keys())

# 工作区根由本文件位置反推(dev/ -> 插件 -> custom_nodes -> 工作区根), 项目搬家后自动跟随
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# 工作流两处并存(2026-11-11 起): stories/workflows 为纳入版本管理的主目录,
# 根 workflows/ 保留 0060~0064 的无数据表版, 两边都要扫
WF_DIRS = [os.path.join(root, "stories", "workflows"), os.path.join(root, "workflows")]
used = {}
for wf_dir in WF_DIRS:
    files = sorted(glob.glob(os.path.join(wf_dir, "*.json")))
    print("scan", os.path.relpath(wf_dir, root), len(files), "files")
    for path in files:
        try:
            wf = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            print("SKIP(unreadable)", os.path.basename(path), e); continue
        for n in wf.get("nodes", []):
            t = n.get("type")
            if t:
                used.setdefault(t, []).append(os.path.basename(path))

missing = {}
for t, files in sorted(used.items()):
    if t in registered or t in WHITELIST: continue
    if UUID_RE.match(t): continue
    missing[t] = files

print("registered node types:", len(registered))
print("distinct types used in workflows:", len(used))
print("MISSING:", len(missing))
for t, files in missing.items():
    print("  -", t, " <-", ", ".join(sorted(set(files))))

# 插件节点加载情况
for key in ("FallingTS", "WorldSurroundPanorama", "WorldPanoramaViews", "WorldRefinePLY"):
    hits = [t for t in registered if key in t]
    print("probe", key, "->", sorted(hits))
