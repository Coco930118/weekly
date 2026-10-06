"""Live OpenAI Threads01 P2: stop -> Coco answer -> same T01 resume -> complete.

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

base_material=(
    "友人が「距離を置きたい」と言った。"
    "私は映画を観た。"
    "次に会う予定は入れなかった。"
    "そのあと、翌週に友人から「話せる？」と連絡が来た。"
    "日付は素材に書かれていない。"
)
answer_date="2026年10月3日"

fixtures=[{
    "id":"TP2",
    "platform":"Threads",
    "content":"",
    "quote":"",
    "theme":"距離の取り方",
    "axis":"感情と関係の「ん？」",
    "_probe_required_facts":["日付","誰が何を言い何をしたか","わたしがしたこと","そのあと起きたこと"],
    "material":base_material,
}]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-threads01-p2","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)
key="posts/probe.json#0"

routing.register_case(key,"Threads","T01","素材確認・事実固定")
state=workspace.get(key)
if not state["theme"] or not state["axis"]:
    workspace.mutate(key,state["revision"],"basis",{"theme":fixtures[0]["theme"],"axis":fixtures[0]["axis"]})

def execute_current():
    state=workspace.get(key)
    return runtime.execute(key,"A","T01",state["revision"],state["candidates"]["A"]["revision"])

require_live_env()

first=execute_current()
if first["kind"]!="stop":
    raise AssertionError(f"Threads P2 missing date should stop, got {first['kind']}")
if first["stop_reason"] not in {"素材不足","事実不明"}:
    raise AssertionError(f"Unexpected Threads P2 stop reason: {first['stop_reason']}")
if "日付" not in (first.get("missing_or_unknown","")+first.get("question_for_coco","")):
    raise AssertionError("Threads P2 did not identify the missing date")

six={
    "部門":"Threads",
    "投稿番号":"TP2",
    "停止工程":first.get("stop_stage") or "②",
    "不足・不明点":first.get("missing_or_unknown") or "日付が不明",
    "現在確認できる事実":first.get("confirmed_facts") or "素材内の明示事実のみ",
    "Cocoへの質問":first.get("question_for_coco") or "日付を教えてください。",
}
queued=routing.stop(key,first["stop_reason"],six)

desk=workspace.desk()
if not desk["queue"] or desk["queue"][0]["id"]!=queued["id"]:
    raise AssertionError("Threads P2 stop is not top of president desk")
if desk["queue"][0]["kind"]!="停止案件":
    raise AssertionError("Threads P2 was not queued as business stop")

routing.resume(key,queued["id"],answer_date)
fixtures[0]["material"]=answer_date+"。"+base_material.replace("日付は素材に書かれていない。","")
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-threads01-p2","posts":fixtures},ensure_ascii=False))

resumed=routing.case(key)
if resumed["employee"]!="T01" or resumed["stage"]!="素材確認・事実固定" or resumed["status"]!="稼働中":
    raise AssertionError(f"Threads P2 did not resume same T01/stage: {resumed}")
if "停止地点から再開" not in [e["action"] for e in routing.events(key)]:
    raise AssertionError("Threads P2 missing resume event")

second=execute_current()
if second["kind"]!="complete":
    raise AssertionError(f"Threads P2 did not complete after answer: {second.get('kind')} / {second.get('stop_reason')}")
check=second.get("completion_check") or {}
if not check.get("ok") or check.get("checklist_count")!=14:
    raise AssertionError(f"Threads P2 completion gate failed after resume: {check}")

body=second["state"]["candidates"]["A"]["fields"].get("content","")
facts=second.get("facts_used",[])
if answer_date not in body and not any(answer_date in str(x) for x in facts):
    raise AssertionError("Threads P2 answered date was not reflected")

routing.complete(key)
routing.vp_gate(key,None)
if not any(x.get("key")==key and x.get("department")=="Threads" for x in workspace.desk()["completed"]):
    raise AssertionError("Threads P2 did not reach president desk completed posts")

with workspace.transaction() as db:
    codes=[row["code"] for row in db.execute("SELECT code FROM executions ORDER BY id")]
for forbidden in {"PUBLISH","X_06","E567"}:
    if forbidden in codes:
        raise AssertionError(f"Forbidden operation recorded: {forbidden}")

print(json.dumps({
    "Threads01_P2":"passed",
    "first_stop_reason":first["stop_reason"],
    "question_for_coco":six["Cocoへの質問"],
    "same_employee":"T01",
    "resume_stage":"素材確認・事実固定",
    "date_reflected":True,
    "completion_gate":"passed",
    "vp_gate":"passed",
    "president_desk":"completed",
    "publish":"not called",
    "x_06":"not called",
    "E567":"not called",
},ensure_ascii=False))
tmp.cleanup()
