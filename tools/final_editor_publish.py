#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final Editor通過後のSNS投稿を公開データとして技術検証する。

文章・ブランド判断はFinal Editorの3軸
（ファン化／深掘りnoteへの布石／ブランド整合性）で完了済みとして扱う。
ここでは旧 full_check.py を再実行せず、JSONと必須項目の反映事故だけを止める。
"""

import glob
import json
import sys

REQUIRED = ("id", "platform", "content")
changed = []
errors = []

for path in sorted(glob.glob("posts/*.json")):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        errors.append(f"{path}: JSONを読めない: {exc}")
        continue

    posts = data.get("posts")
    if posts is None:
        continue
    if not isinstance(posts, list):
        errors.append(f"{path}: posts が配列ではない")
        continue

    dirty = False
    for index, post in enumerate(posts):
        if not isinstance(post, dict):
            errors.append(f"{path}: posts[{index}] がオブジェクトではない")
            continue
        if post.get("final_editor_status") != "pending_check":
            continue

        missing = [key for key in REQUIRED if not post.get(key)]
        if missing:
            pid = post.get("id") or f"posts[{index}]"
            errors.append(f"{path}: {pid}: 必須項目が空: {', '.join(missing)}")
            continue

        if post["platform"] not in ("X", "Threads"):
            errors.append(
                f"{path}: {post['id']}: platform が対象外: {post['platform']}"
            )
            continue

        post["final_editor_status"] = "public_ok"
        dirty = True

    if dirty:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        changed.append(path)

if errors:
    for error in errors:
        print("technical check failed:", error)
    sys.exit(1)

print("public_ok:", ", ".join(changed) if changed else "none")
