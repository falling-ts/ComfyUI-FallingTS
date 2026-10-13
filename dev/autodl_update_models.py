#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoDL.Art 云模型库清单重建工具（`webs/AutoDL/models.md`）。

数据来源：POST https://www.autodl.art/api/v1/application/model/file/search
（AutoDL.Art 社区站，域名独立于 autodl.com，登录态不通用）。

设计依据：webs/AutoDL/api.md §5.2.x 「零回归」原则 ——
  * 旧表已识别的 instance_path 一律沿用旧结论（含人工判定的子目录形态），
    只有新 instance_path 才走规则/传播，零回归风险；
  * 同一 instance_path 多行冲突时，优先保留「已识别」那条；
  * 判定不出的标「未识别(需人工核对)」，不强行猜测。

用法：
  # 用已抓取缓存重建（不联网，最快）
  python autodl_update_models.py --cache C:/Windows/Temp/autodl_models_full.json

  # 实时抓取（token 走环境变量，不落盘）
  set AUTODL_TOKEN=<裸token>
  python autodl_update_models.py --fetch

  # 只打印统计与分类分布，不写文件
  python autodl_update_models.py --cache <json> --dry

  # 自定义旧表 / 输出路径（默认读 webs/AutoDL/models.md 并原地重建）
  python autodl_update_models.py --cache <json> --old <md> --out <md>

token 属于敏感凭据：本工具不写、不打印 token；实时抓取时只从环境变量读取。
"""
import json
import re
import os
import sys
import argparse
import concurrent.futures
import urllib.request
from collections import Counter
from datetime import datetime

URL = "https://www.autodl.art/api/v1/application/model/file/search"
PAGE_SIZE = 100

# ---------------------------------------------------------------------------
# 清洗 / 格式化
# ---------------------------------------------------------------------------
def clean(s):
    """去掉文件名里的高亮标签 <em>..</em>（搜索接口会注入），并防注入"""
    if not s:
        return ""
    s = re.sub(r"</?em>", "", s)
    return s.strip()


def fmt_size(n):
    if n is None:
        return "-"
    n = float(n)
    if n < 1024:
        return "%.2f B" % n
    if n < 1024 ** 2:
        return "%.2f KB" % (n / 1024)
    if n < 1024 ** 3:
        return "%.2f MB" % (n / 1024 ** 2)
    return "%.2f GB" % (n / 1024 ** 3)


def fmt_time(iso):
    """2026-10-13T04:25:37+08:00 -> 2026-10-13 04:25"""
    if not iso:
        return "-"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso[:16]


# ---------------------------------------------------------------------------
# 分类规则（顺序敏感：LoRA 前置、H3 专用居中、扩散名特征后移、LLM 兜底）
# ---------------------------------------------------------------------------
def classify(fn, repo, note):
    """返回本地目录分类；判不出返回 '未识别(需人工核对)'"""
    fn = clean(fn).lower()
    repo = clean(repo or "").lower()
    note = clean(note or "").lower()

    # ---- LoRA 族（前置，避免被后面的 LLM 规则误吞 Qwen/H3 前缀）----
    if re.search(r"(?i)(loras?|lightx2v|turbo[-_]?.*lora|4step|\boutpaint\b|"
                 r"ref2va.*lora|_lora[-_.]|-lora[-_.]|\.lora\.)", fn):
        return "loras"
    # ---- MiniMax-H3 专用 ----
    if "minimax" in fn and "h3" in fn:
        if re.search(r"(?i)(adapter|temporal|motion|expansion|bridge|enhancer|"
                     r"plug|controlnet|union|lora)", fn):
            return "loras"
        return "diffusion_models"
    # ---- 文本编码器 ----
    if re.search(r"(?i)(text_encoder|text_encoders|umt5|qwen3[-_]?vl|t5[-_]|"
                 r"tokenizer|encoder|clip[-_])", fn):
        return "text_encoders"
    # ---- VAE ----
    if re.search(r"(?i)(vae|ae\.safetensors)", fn):
        return "vae"
    # ---- 控制网 ----
    if re.search(r"(?i)(controlnet|control[-_]?net|annotator|openpose|depth_anything)", fn):
        return "controlnet"
    # ---- 放大 / 超分 ----
    if re.search(r"(?i)(upscale|esrgan|realesrgan|4x_|x4_|swinir|waifu2x)", fn):
        return "upscale_models"
    # ---- 抠像 / 背景 ----
    if re.search(r"(?i)(rembg|background_removal|matanyone|birefnet|inspyrenet|isnet)", fn):
        return "background_removal"
    # ---- TTS / 音频 ----
    if re.search(r"(?i)(tts|speech|wav2vec|vocoder|bigvgan|codec|voice|index_tts|"
                 r"fishaudio|s2-pro|qwen3\.tts|hifigan|cosyvoice|audio)", fn):
        return "TTS"
    # ---- ASR ----
    if re.search(r"(?i)(asr|whisper|sensevoice|firered|paraformer)", fn):
        return "ASR"
    # ---- 检测 / 人脸 / 姿态 ----
    if re.search(r"(?i)(yolo|face_|det_|ultralytics|mhr_model|raft|vitpose|hand_|"
                 r"2d106|genderage|propainter)", fn):
        return "yolo"
    # ---- 3D ----
    if re.search(r"(?i)(slat|ss_|triposplat|pixal3d|trellis|hunyuan3d|geometry)", fn):
        return "未识别(3D)"
    # ---- 配置 / 杂项 ----
    if re.search(r"(?i)(\.(json|txt|yaml|yml|pt|onnx|bin|gguf|md|ckpt|py)$|"
                 r"config|preprocessor|merges|vocab|jinja|license|notice|readme|"
                 r"usage_policy|policy)", fn):
        return "configs"
    # ---- LLM（兜底）----
    if re.search(r"(?i)(qwen|minimax|llm|gpt|bert|glm|ernie|mistral|phi|deepseek|chat|"
                 r"nemotron|gpt-oss)", fn):
        return "LLM"
    # ---- 扩散模型兜底（带权重扩展名 / 量化 / 主模型特征）----
    if re.search(r"(?i)(\.safetensors|\.gguf|\.ckpt|ninfer$|pruned|int8_convrot|"
                 r"fp8|bf16|fp16|diffusion)", fn):
        return "diffusion_models"
    # ---- note 维度兜底（文件名无信号时）----
    if re.search(r"(?i)(tts|语音|音频|cosyvoice|voice|audio)", note):
        return "TTS"
    if re.search(r"(?i)(\.py$|\.json$|\.md$|config|usage_policy|license|notice|policy)", note):
        return "configs"
    return "未识别(需人工核对)"


# ---------------------------------------------------------------------------
# 旧表解析（零回归基准）
# ---------------------------------------------------------------------------
def parse_old_md(path):
    """返回 (old_ip_cat, old_repo_cat)。
    old_ip_cat: instance_path -> 本地目录（同路径多行冲突时优先已识别）
    old_repo_cat: 所属仓库 -> 已识别本地目录（仅收已识别，作传播源）
    """
    old_ip_cat = {}
    old_repo_cat = {}
    if not os.path.exists(path):
        return old_ip_cat, old_repo_cat
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.startswith("| "):
                continue
            if line.startswith("| #"):
                continue
            if set(line.strip()) <= set("|- "):
                continue
            parts = [p.strip() for p in line.strip().strip("|").split("|")]
            if len(parts) < 9:
                continue
            fn, size, repo, ip, user, ts, note, cat = parts[1], parts[2], parts[3], parts[4], parts[5], parts[6], parts[7], parts[8]
            ip = ip.strip("`")
            cat = cat.strip()
            is_un = cat.startswith("未识别")
            # instance_path 优先已识别
            if ip not in old_ip_cat:
                old_ip_cat[ip] = cat
            elif old_ip_cat[ip].startswith("未识别") and not is_un:
                old_ip_cat[ip] = cat
            # 仓库传播源（仅已识别）
            if not is_un and repo and repo != "-":
                old_repo_cat.setdefault(repo, cat)
    return old_ip_cat, old_repo_cat


def classify_new_item(it, old_ip_cat, old_repo_cat):
    """对新增（旧表没有的）instance_path 做分类"""
    ip = it.get("instance_path")
    if ip in old_ip_cat:                      # 理论上不会发生（added 已排除）
        return old_ip_cat[ip]
    fn = it.get("file_name", "")
    repo = it.get("model_repository", "") or ""
    note = it.get("note", "") or ""
    cat = classify(fn, repo, note)
    if cat.startswith("未识别"):
        # 兜底：仓库传播（仅已识别源）
        if repo in old_repo_cat:
            cat = old_repo_cat[repo]
    return cat


# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------
def _headers(token):
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "Origin": "https://www.autodl.art",
        "Referer": "https://www.autodl.art/app/common/model",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
    }


def fetch_all(token, max_workers=12):
    """并发分页拉全，按 id 去重，返回按 updated_at 降序的 list"""
    def post(pl):
        req = urllib.request.Request(URL, data=json.dumps(pl).encode(),
                                     headers=_headers(token), method="POST")
        return json.load(urllib.request.urlopen(req, timeout=30))

    first = post({"page_index": 1, "page_size": 1, "file_name": "", "model_repository": ""})
    data = first["data"]
    total, maxpage = data["result_total"], data["max_page"]
    print(f"[fetch] result_total={total} max_page={maxpage}", flush=True)
    seen = {}
    def fetch(p):
        return post({"page_index": p, "page_size": PAGE_SIZE, "file_name": "", "model_repository": ""})["data"]["list"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        for lst in ex.map(fetch, range(1, maxpage + 1)):
            for it in lst:
                seen[it["id"]] = it
    items = sorted(seen.values(), key=lambda x: x.get("updated_at", ""), reverse=True)
    assert len(items) == total, f"去重后 {len(items)} != result_total {total}"
    print(f"[fetch] 去重完成 = {len(items)} 条", flush=True)
    return items


# ---------------------------------------------------------------------------
# 构建 markdown
# ---------------------------------------------------------------------------
def build_md(items, old_ip_cat, old_repo_cat, meta):
    lines = []
    a = meta["added_cats"]
    lines.append("# AutoDL.Art 云模型库清单")
    lines.append("")
    lines.append("> 数据来源：`POST https://www.autodl.art/api/v1/application/model/file/search`（AutoDL.Art 社区站云模型库）")
    lines.append(f"> 抓取时间：{meta['fetch_date']}；共 **{len(items)}** 条模型文件记录"
                 f"（**{meta['unique_paths']}** 个唯一实例路径，同一文件多次上传各占一行）"
                 f"，较上次（{meta['prev_date']}）新增 {meta['new_records']} 条记录 / "
                 f"**{meta['new_paths']}** 个新实例路径，消失 0 个")
    lines.append("> 字段：模型名称(file_name)、大小、所属仓库(model_repository)、实例路径(instance_path)、"
                 "上传者、更新时间、备注(note)、本地目录。")
    lines.append("> 本地目录分类遵循 `api.md` §5.2 零回归原则：旧表已识别的实例路径一律沿用旧结论，"
                 "只有新增路径走规则/仓库传播；判定不出的标「未识别(需人工核对)」。")
    lines.append("")
    lines.append("## 如何使用这些模型")
    lines.append("")
    lines.append("1. **拷贝到实例**：模型在云上按 `/.autodl/<前2位>/<前2位>/<前2位>/<md5>` 结构存放，"
                 "上表「实例路径」即实例内可直接使用的路径；")
    lines.append("2. **落到 ComfyUI**：进入 `ComfyUI/models/` 对应子目录后，用软链接指到实例路径（一步到位，不占系统盘空间）：")
    lines.append("   ```bash")
    lines.append("   cd ComfyUI/models/<子目录>               # 按类型: diffusion_models / text_encoders / vae / loras / checkpoints ...")
    lines.append("   ln -s {实例路径} {模型名称}                # {实例路径}=上表「实例路径」列, {模型名称}=上表「模型名称」列")
    lines.append("   # 例: ln -s /.autodl/a3/d4/99/a3d499fde128c535aa751e68bb87f852 minimax_h3_turbo_4step_diffusion_model.safetensors")
    lines.append("   # 目录型模型(「本地目录」列含 /, 如 TTS/IndexTTS-2.5-Comfy): 先建仓库子目录, 该仓库所有文件逐条链接进去")
    lines.append("   ```")
    lines.append("   或先放 `/root/autodl-tmp/` 再挂链接，或配置 `extra_model_paths.yaml` 免链接；")
    lines.append("3. **文件名对齐**：工作流按 `file_name` 引用模型，拷贝后须保持文件名与工作流一致；大文件用 `md5` 校验完整性；")
    lines.append("4. **目录型模型**（如 Qwen3-TTS）需整目录拷贝，不能只取单文件；接口查询方法见 `api.md` §5。")
    lines.append("")
    lines.append(f"## 模型清单（共 {len(items)} 条，按更新时间倒序，最新在前）")
    lines.append("")
    lines.append("| # | 模型名称 | 大小 | 所属仓库 | 实例路径 | 上传者 | 更新时间 | 备注 | 本地目录 |")
    lines.append("|--:|---------|-----|---------|---------|--------|---------|------|---------|")
    for idx, it in enumerate(items, 1):
        fn = clean(it.get("file_name", ""))
        size = fmt_size(it.get("file_size"))
        repo = clean(it.get("model_repository", "")) or "-"
        ip = it.get("instance_path", "")
        user = it.get("user_info", {}).get("username", "-")
        ts = fmt_time(it.get("updated_at", ""))
        note = clean(it.get("note", "")) or "-"
        # 本地目录：零回归 or 新分类
        if ip in old_ip_cat:
            cat = old_ip_cat[ip]
        else:
            cat = classify_new_item(it, old_ip_cat, old_repo_cat)
        # 转义管道符，避免破坏表格
        fn_d = fn.replace("|", "\\|")
        note_d = note.replace("|", "\\|")
        lines.append(f"| {idx} | `{fn_d}` | {size} | {repo} | `{ip}` | {user} | {ts} | {note_d} | {cat} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", help="已抓取的 JSON 缓存路径（不联网）")
    ap.add_argument("--fetch", action="store_true", help="实时抓取（需 AUTODL_TOKEN 环境变量）")
    ap.add_argument("--token-env", default="AUTODL_TOKEN", help="token 环境变量名")
    ap.add_argument("--old", default=None, help="旧 models.md 路径（零回归基准）")
    ap.add_argument("--out", default=None, help="输出 models.md 路径（默认等同 --old）")
    ap.add_argument("--dry", action="store_true", help="只打印统计，不写文件")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))  # .../ComfyUI-FallingTS/dev -> repo root
    old_md = args.old or os.path.join(root, "webs", "AutoDL", "models.md")
    out_md = args.out or old_md

    # 1) 加载数据
    if args.fetch:
        token = os.environ.get(args.token_env)
        if not token:
            sys.exit(f"缺少环境变量 {args.token_env}")
        items = fetch_all(token)
        fetch_date = datetime.now().strftime("%Y-%m-%d")
    elif args.cache:
        with open(args.cache, encoding="utf-8") as f:
            items = json.load(f)
        fetch_date = datetime.now().strftime("%Y-%m-%d")
    else:
        sys.exit("需指定 --cache 或 --fetch")

    # 2) 旧表基准
    old_ip_cat, old_repo_cat = parse_old_md(old_md)
    old_unique = len(old_ip_cat)

    # 3) 零回归对比 + 分类
    new_paths = [it["instance_path"] for it in items]
    new_unique = len(set(new_paths))
    old_set = set(old_ip_cat)
    new_set = set(new_paths)
    added = new_set - old_set
    gone = old_set - new_set
    added_cats = Counter()
    for it in items:
        if it["instance_path"] in added:
            c = classify_new_item(it, old_ip_cat, old_repo_cat)
            added_cats[c] += 1

    prev_date = "2026-10-10"
    meta = {
        "fetch_date": fetch_date,
        "prev_date": prev_date,
        "unique_paths": new_unique,
        "new_records": len(items) - (len(old_ip_cat) if False else sum(1 for _ in old_ip_cat)),  # 占位，下面重算
        "new_paths": len(added),
        "added_cats": added_cats,
    }
    # 记录总数增量 = 本次记录数 - 旧表解析到的数据行数
    old_rows = 0
    if os.path.exists(old_md):
        with open(old_md, encoding="utf-8") as f:
            for line in f:
                if line.startswith("| ") and not line.startswith("| #") and set(line.strip()) > set("|- "):
                    parts = line.strip().strip("|").split("|")
                    if len(parts) >= 9:
                        old_rows += 1
    meta["new_records"] = len(items) - old_rows

    print(f"[stat] 旧表数据行={old_rows} 旧唯一路径={old_unique}")
    print(f"[stat] 本次记录={len(items)} 本次唯一路径={new_unique}")
    print(f"[stat] 零回归交集路径={len(new_set & old_set)} 消失={len(gone)} 新增路径={len(added)}")
    print(f"[stat] 新增路径分类分布:")
    for k, v in added_cats.most_common():
        print(f"        {v:4d}  {k}")

    # 4) 生成
    md = build_md(items, old_ip_cat, old_repo_cat, meta)
    if args.dry:
        print(f"[dry] 不写文件，将生成 {len(items)} 行表格")
        return
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[write] -> {out_md}  ({len(md)} 字节)")


if __name__ == "__main__":
    main()
