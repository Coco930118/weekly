"""Interview employee (取材社員) live probe — single fixed material, run once.

Technical connectivity/behavior probe only (atelier/canon/interview.md is used
as the real instruction text, but the material below is a synthetic test
scenario, not a real Coco episode). Reports what the model actually returned
at each of the three AI-backed stages (fill points / propose drafts /
generalize) verbatim, plus usage, with no post-processing or cleanup.

Run via GitHub Actions workflow_dispatch where ANTHROPIC_API_KEY is injected
from repository secrets. Requires ATELIER_ANTHROPIC_LIVE=1.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from atelier.server.server import Workspace
from atelier.server.ai_runtime import AIRuntime
from atelier.server.routing import RoutingEngine


def require_live_env():
    if os.environ.get("ATELIER_ANTHROPIC_LIVE") != "1":
        raise SystemExit("ATELIER_ANTHROPIC_LIVE=1 is required")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is missing")


# 固定の原文1本。技術確認用の合成シナリオ（実際のCoco素材ではない）。
RAW_MATERIAL = (
    "先週の火曜日、後輩が「このやり方で合ってますか」と聞いてきた。"
    "わたしはその場で手順を直して見せた。その後輩は今も同じやり方を続けている。"
)


def main():
    require_live_env()
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    for folder in ["posts", "notes", "atelier/config", "atelier/canon"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    for name in ["employees.json", "workflow.json"]:
        (root / "atelier/config" / name).write_bytes((ROOT / "atelier/config" / name).read_bytes())
    for name in ["interview.md", "x_post.md", "threads_post.md"]:
        (root / "atelier/canon" / name).write_bytes((ROOT / "atelier/canon" / name).read_bytes())
    (root / "posts/index.json").write_text(json.dumps({"weeks": []}))
    (root / "notes/index.json").write_text(json.dumps({"notes": []}))

    workspace = Workspace(root, root / "work.sqlite3")
    runtime = AIRuntime(workspace)
    routing = RoutingEngine(workspace)
    case_id = "interview-live-probe#1"

    report = {"raw_material": RAW_MATERIAL}

    stage2 = runtime.interview_fill_points(RAW_MATERIAL)
    report["stage2_points"] = stage2["points"]
    report["stage2_missing"] = stage2["missing"]
    report["stage2_provider"] = stage2.get("_provider")

    routing.material_start(case_id, "X", "MATERIAL", RAW_MATERIAL, stage2["points"])
    routing.record_provider_usage(case_id, "工程2", stage2.get("_provider"))

    summary = routing.material_summary(case_id)
    stage3 = runtime.interview_propose_drafts(summary["raw_material"], summary["organized_material"])
    report["stage3_drafts"] = stage3["drafts"]
    report["stage3_provider"] = stage3.get("_provider")
    routing.material_propose(case_id, stage3["drafts"])
    routing.record_provider_usage(case_id, "工程3", stage3.get("_provider"))

    selection = "A" if stage3["drafts"] else "案なし・自分で書く"
    routing.material_select(case_id, selection)

    summary = routing.material_summary(case_id)
    selected_draft = summary["drafts"][0] if selection == "A" and summary.get("drafts") else None
    stage5 = runtime.interview_generalize(
        summary["raw_material"], summary["organized_material"], summary["department"],
        {"選択": selection, "選んだ案": selected_draft, "追記": ""},
    )
    report["stage5_public_material"] = stage5["public_material"]
    report["stage5_smell_flags"] = stage5.get("smell_flags")
    report["stage5_provider"] = stage5.get("_provider")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    tmp.cleanup()


if __name__ == "__main__":
    main()
