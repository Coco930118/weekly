"""Live OpenAI Threads01 P1 completion-gate probe.

Requires:
- six canon stages in order
- mechanical exit gate: 6 paragraphs + 14 recorded stage-④ checks
- VP routing only after the gate passes
No publish/x_06/E567 code is called.
"""
import json
import os
from pathlib import Path
import re
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
    "atelier/canon/threads_post.md",
]:
    target=root/copy_path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((ROOT/copy_path).read_bytes())

material=(
    "2026年10月3日、友人が「距離を置きたい」と言った。"
    "私は映画を観た。"
    "次に会う予定は入れなかった。"
    "そのあと、翌週に友人から「話せる？」と連絡が来た。"
)

fixtures=[{
    "id":"TP1",
    "platform":"Threads",
    "content":"",
    "quote":"",
    "theme":"距離の取り方",
    "axis":"感情と関係の「ん？」",
    "_probe_required_facts":["日付","誰が何を言い何をしたか","わたしがしたこと","そのあと起きたこと"],
    "material":material,
}]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-threads01-completion-gate","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)

key="posts/probe.json#0"
routing.register_case(key,"Threads","T01","素材確認・事実固定")
state=workspace.get(key)
if not state["theme"] or not state["axis"]:
    workspace.mutate(
        key,state["revision"],"basis",
        {"theme":fixtures[0]["theme"],"axis":fixtures[0]["axis"]}
    )

require_live_env()
state=workspace.get(key)
result=runtime.execute(
    key,"A","T01",
    state["revision"],state["candidates"]["A"]["revision"]
)

if result["kind"]!="complete":
    print(json.dumps({
        "Threads01_P1_diagnostic":{
            "kind":result.get("kind"),
            "stop_reason":result.get("stop_reason"),
            "stop_stage":result.get("stop_stage"),
            "continue_stage":result.get("continue_stage"),
            "format_failures":result.get("format_failures"),
            "missing_or_unknown":result.get("missing_or_unknown"),
            "question_for_coco":result.get("question_for_coco"),
        }
    },ensure_ascii=False))
    raise AssertionError(f"Threads01 P1 expected format-complete, got {result['kind']}")

check=result.get("completion_check") or {}
if not check.get("ok"):
    raise AssertionError(f"Threads01 completion gate did not pass: {check}")
if check.get("checklist_count")!=14:
    raise AssertionError(f"Threads01 expected 14 recorded checks: {check}")

saved=result["state"]
body=saved["candidates"]["A"]["fields"].get("content","")
paragraphs=[p.strip() for p in re.split(r"\n\s*\n",body.strip()) if p.strip()]
if len(paragraphs)!=6:
    raise AssertionError(f"Threads01 final body is not 6 paragraphs: {paragraphs}")

stage4=next(x for x in reversed(result["stage_outputs"]) if x["stage"]=="④")
checklist=stage4.get("checklist") or []
if len(checklist)!=14:
    raise AssertionError(f"Threads01 stage ④ checklist is not 14: {checklist}")

# VP is called only after the mechanical completion gate has passed.
routing.complete(key)
routing.vp_gate(key,None)
desk=workspace.desk()
if not any(x.get("key")==key and x.get("department")=="Threads" for x in desk["completed"]):
    raise AssertionError("Threads01 P1 did not reach completed posts after format gate")

events=routing.events(key)
if [e["action"] for e in events][-2:]!=["完成","3点確認OK"]:
    raise AssertionError("Threads01 route did not finish completion -> VP gate")

with workspace.transaction() as db:
    exec_codes=[row["code"] for row in db.execute("SELECT code FROM executions ORDER BY id")]
for forbidden in {"PUBLISH","X_06","E567"}:
    if forbidden in exec_codes:
        raise AssertionError(f"Forbidden operation was recorded: {forbidden}")

print(json.dumps({
    "Threads01_P1":"passed",
    "completion_gate":"6 paragraphs + 14 checks",
    "checklist":checklist,
    "body":body,
    "paragraph_count":len(paragraphs),
    "checklist_count":len(checklist),
    "vp_gate":"passed",
    "president_desk":"completed",
    "publish":"not called",
    "x_06":"not called",
    "E567":"not called",
},ensure_ascii=False))
tmp.cleanup()
