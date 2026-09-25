#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final Editor完成後のnoteを公開データとして技術検証する。

文章・販売判断・ブランド判断はFinal Editorの3軸チェックが正典。
ここではClaude生成時の note_check.py を再実行せず、反映事故だけを止める。
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = ("note_id", "title", "description", "outcome_promise", "content_markdown")
changed = []
failed = []

def md2html(md):
    def inline(s):
        return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    out = []
    for block in md.split("\n\n"):
        b = block.strip()
        if not b:
            continue
        if b == "---":
            out.append("<hr>")
            continue
        if b.startswith("## "):
            out.append("<h2>" + inline(b[3:].strip()) + "</h2>")
            continue
        lines = [line.strip() for line in b.split("\n") if line.strip()]
        out.append("<p>" + "<br>".join(inline(line) for line in lines) + "</p>")
    return "".join(out)

for path in sorted(glob.glob(os.path.join(ROOT, "notes", "note_*.json"))):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        continue
    if data.get("note_final_editor_status") != "pending_check":
        continue

    errors = []
    for key in REQUIRED:
        if not data.get(key):
            errors.append(f"{key} が空")

    md = data.get("content_markdown") or ""
    if "content_html" in data and data.get("content_html") != md2html(md):
        errors.append("content_markdown と content_html がずれている")

    status = "check_failed" if errors else "public_ok"
    data["note_final_editor_status"] = status
    if errors:
        data["note_final_editor_check_errors"] = errors
        failed.append(os.path.relpath(path, ROOT))
        print(os.path.relpath(path, ROOT) + ": " + " / ".join(errors))
    else:
        data.pop("note_final_editor_check_errors", None)
        print(os.path.relpath(path, ROOT) + ": technical check OK")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    changed.append(os.path.relpath(path, ROOT))

print("updated:", ", ".join(changed) if changed else "none")
if failed:
    print("technical check failed:", ", ".join(failed))
