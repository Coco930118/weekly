"""Live OpenAI X01 P1 completion-gate probe.

Revalidates only the previously invalidated "completed" portion of X01 P1:
- same X01 runs canon stages in order
- mechanical exit gate requires 4 lines + 3 recorded facts
- only after the exit gate passes may routing.complete / VP gate run
No publish/x_06/E567 code is called.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from atelier.server.server import Workspace
from atelier.server.ai_runtime import AIRuntime
from atelier.server.routing import RoutingEngine


def require_live_env():
    if os.environ.get("ATELIER_OPENAI_LIVE")!="1":
        raise SystemExit("ATELIER_OPENAI_LIVE=1 is required")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing")


tmp=tempfile.TemporaryDirectory()
root=Path(tmp.name)
for folder in ["posts","notes","atelier/config","atelier/canon"]:
    (root/folder).mkdir(parents=True,exist_ok=True)
for copy_path in [
    "atelier/config/employees.json",
    "atelier/config/workflow.json",
    "atelier/canon/x_post.md",
]:
    target=root/copy_path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((ROOT/copy_path).read_bytes())

material=(
    "2026年10月3日、店長が「この判断は自分で決めたい」と言ったあと、"
    "「どうしましょう」と最後の判断をこちらに戻してきた。"
    "私は条件と予算だけ伝え、最後の判断を店長に任せた。"
    "そのあと、店長から「この案で進めます」と返事があった。"
)

fixtures=[{
    "id":"XP1",
    "platform":"X",
    "content":"",
    "quote":"",
    "theme":"現場の判断",
    "axis":"仕事・現場の「ん？」",
    "_probe_required_facts":["日付","誰が何を言い、そのとき何が起きたか","わたしがしたこと","現場で起きたこと"],
    "material":material,
}]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-x01-completion-gate","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)

key="posts/probe.json#0"
routing.register_case(key,"X","X01","素材確認・事実固定")
state=workspace.get(key)
if not state["theme"] or not state["axis"]:
    workspace.mutate(
        key,state["revision"],"basis",
        {"theme":fixtures[0]["theme"],"axis":fixtures[0]["axis"]}
    )

require_live_env()
state=workspace.get(key)
result=runtime.execute(
    key,"A","X01",
    state["revision"],state["candidates"]["A"]["revision"]
)

if result["kind"]!="complete":
    print(json.dumps({
        "X01_P1_diagnostic":{
            "kind":result.get("kind"),
            "stop_reason":result.get("stop_reason"),
            "stop_stage":result.get("stop_stage"),
            "continue_stage":result.get("continue_stage"),
            "format_failures":result.get("format_failures"),
            "missing_or_unknown":result.get("missing_or_unknown"),
            "question_for_coco":result.get("question_for_coco"),
        }
    },ensure_ascii=False))
    raise AssertionError(f"X01 P1 expected format-complete, got {result['kind']}")

check=result.get("completion_check") or {}
if not check.get("ok"):
    raise AssertionError(f"X01 completion gate did not pass: {check}")
if check.get("facts_count")!=3:
    raise AssertionError(f"X01 expected 3 recorded facts: {check}")

saved=result["state"]
body=saved["candidates"]["A"]["fields"].get("content","")
lines=[line for line in body.splitlines() if line.strip()]
if len(lines)!=4:
    raise AssertionError(f"X01 final body is not 4 lines: {lines}")

stage2=next(x for x in result["stage_outputs"] if x["stage"]=="②")
facts=stage2.get("facts_used") or []
if len(facts)!=3:
    raise AssertionError(f"X01 stage ② facts are not exactly 3: {facts}")

# VP is called only after the mechanical completion gate has passed.
routing.complete(key)
routing.vp_gate(key,None)
desk=workspace.desk()
if not any(x.get("key")==key and x.get("department")=="X" for x in desk["completed"]):
    raise AssertionError("X01 P1 did not reach completed posts after format gate")

events=routing.events(key)
if [e["action"] for e in events][-2:]!=["完成","3点確認OK"]:
    raise AssertionError("X01 route did not finish completion -> VP gate")

with workspace.transaction() as db:
    exec_codes=[row["code"] for row in db.execute("SELECT code FROM executions ORDER BY id")]
for forbidden in {"PUBLISH","X_06","E567"}:
    if forbidden in exec_codes:
        raise AssertionError(f"Forbidden operation was recorded: {forbidden}")

print(json.dumps({
    "X01_P1":"passed",
    "completion_gate":"4 lines + 3 facts",
    "facts":facts,
    "body":body,
    "line_count":len(lines),
    "facts_count":len(facts),
    "vp_gate":"passed",
    "president_desk":"completed",
    "publish":"not called",
    "x_06":"not called",
    "E567":"not called",
},ensure_ascii=False))
tmp.cleanup()
