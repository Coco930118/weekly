"""Live OpenAI Threads01 probe: P1 only.

Requires OPENAI_API_KEY and ATELIER_OPENAI_LIVE=1.
P2/P3 remain unexecuted until Threads01 P1 completes.
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
    "atelier/canon/threads_post.md",
]:
    target=root/copy_path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((ROOT/copy_path).read_bytes())

material=(
    "2026年10月3日、友人から「少し距離を置きたい」とメッセージが届いた。"
    "その日は返信を待たず、前から見たかった映画を一本観た。"
    "私は次に会う予定を入れなかった。"
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
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-threads01-probe","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)


def init_case():
    key="posts/probe.json#0"
    routing.register_case(key,"Threads","T01","素材確認・事実固定")
    state=workspace.get(key)
    if not state["theme"] or not state["axis"]:
        workspace.mutate(
            key,state["revision"],"basis",
            {"theme":fixtures[0]["theme"],"axis":fixtures[0]["axis"]}
        )
    return key


def execute_current(key):
    state=workspace.get(key)
    return runtime.execute(
        key,"A","T01",
        state["revision"],state["candidates"]["A"]["revision"]
    )


require_live_env()
key=init_case()
result=execute_current(key)
if result["kind"]!="complete":
    print(json.dumps({
        "Threads01_P1_diagnostic":{
            "kind":result.get("kind"),
            "stop_reason":result.get("stop_reason"),
            "stop_stage":result.get("stop_stage"),
            "missing_or_unknown":result.get("missing_or_unknown"),
            "question_for_coco":result.get("question_for_coco"),
            "provider":result.get("provider"),
        }
    },ensure_ascii=False))
    raise AssertionError(f"Threads01 P1 expected complete, got {result['kind']} / {result.get('stop_reason')}")

events=routing.events(key)
stage_outputs=result.get("stage_outputs",[])
stage_names=[x.get("stage") for x in stage_outputs]
if stage_names!=["①","ひとこと選び","②","③","④","⑤"]:
    raise AssertionError(f"Threads01 orchestration order mismatch: {stage_names}")
completed_stage_events=[
    e["target"] for e in events if e["action"]=="工程完了"
]
if completed_stage_events!=["①","ひとこと選び","②","③","④","⑤"]:
    raise AssertionError(f"workflow_events stage order mismatch: {completed_stage_events}")

state=result["state"]
content=state["candidates"]["A"]["fields"].get("content","")
stage4=next((x.get("content","") for x in stage_outputs if x.get("stage")=="④"),"")
if not stage4 or content!=stage4:
    raise AssertionError("Final saved content was not preserved from stage ④ through stage ⑤ review")
provider=result.get("provider",{})

with workspace.transaction() as db:
    exec_codes=[row["code"] for row in db.execute("SELECT code FROM executions ORDER BY id")]
for forbidden in {"PUBLISH","X_06","E567"}:
    if forbidden in exec_codes:
        raise AssertionError(f"Forbidden operation was recorded: {forbidden}")

print(json.dumps({
    "Threads01_orchestration":"passed",
    "material":material,
    "employee_output":content,
    "status":provider.get("status"),
    "reasoning_tokens":provider.get("reasoning_tokens"),
    "output_tokens":provider.get("output_tokens"),
    "max_output_tokens":provider.get("max_output_tokens"),
    "stage_order":["①","ひとこと選び","②","③","④","⑤"],
    "vp_gate":"not tested in this step",
    "president_desk":"not tested in this step",
    "publish":"not called",
    "x_06":"not called",
    "E567":"not called",
},ensure_ascii=False))
tmp.cleanup()
