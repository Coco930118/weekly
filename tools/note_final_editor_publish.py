#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final Editor後のnoteだけを既存 note_check.py で再検査し、状態を確定する。"""
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, "tools", "note_check.py")
changed = []
failed = []

for path in sorted(glob.glob(os.path.join(ROOT, "notes", "note_*.json"))):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        continue
    if data.get("note_final_editor_status") != "pending_check":
        continue

    print(f"\n=== Final Editor re-note_check: {os.path.relpath(path, ROOT)} ===")
    result = subprocess.run([sys.executable, CHECK, path], cwd=ROOT)
    data["note_final_editor_status"] = "public_ok" if result.returncode == 0 else "check_failed"
    if result.returncode != 0:
        failed.append(os.path.relpath(path, ROOT))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    changed.append(os.path.relpath(path, ROOT))

print("\nupdated:", ", ".join(changed) if changed else "none")
if failed:
    print("note_check failed:", ", ".join(failed))
