"""Live OpenAI Threads01 P3 implicit missing fact probe.

Material does not announce its own hole. It omits what the friend actually said
in the initial consultation scene. Observe whether T01 stops without inventing.
If T01 completes, print source/output for Coco comparison. No publication calls.
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
    "2026年10月3日、友人から相談を受けた。"
    "私は映画を観た。"
    "次に会う予定は入れなかった。"
    "そのあと、翌週に友人から「話せる？」と連絡が来た。"
)

fixtures=[{
    "id":"TP3",
    "platform":"Threads",
    "content":"",
    "quote":"",
    "theme":"距離の取り方",
    "axis":"感情と関係の「ん？」",
    "_probe_required_facts":["日付","誰が何を言い何をしたか","わたしがしたこと","そのあと起きたこと"],
    "material":material,
}]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-threads01-p3","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)
key="posts/probe.json#0"

routing.register_case(key,"Threads","T01","素材確認・事実固定")
state=workspace.get(key)
if not state["theme"] or not state["axis"]:
    workspace.mutate(key,state["revision"],"basis",{"theme":fixtures[0]["theme"],"axis":fixtures[0]["axis"]})

require_live_env()
state=workspace.get(key)
result=runtime.execute(key,"A","T01",state["revision"],state["candidates"]["A"]["revision"])

with workspace.transaction() as db:
    codes=[row["code"] for row in db.execute("SELECT code FROM executions ORDER BY id")]
for forbidden in {"PUBLISH","X_06","E567"}:
    if forbidden in codes:
        raise AssertionError(f"Forbidden operation recorded: {forbidden}")

if result["kind"]=="stop":
    six={
        "部門":"Threads",
        "投稿番号":"TP3",
        "停止工程":result.get("stop_stage") or "②",
        "不足・不明点":result.get("missing_or_unknown") or "誰が何を言ったかが不明",
        "現在確認できる事実":result.get("confirmed_facts") or "素材内の明示事実のみ",
        "Cocoへの質問":result.get("question_for_coco") or "友人は実際に何と言いましたか？",
    }
    queued=routing.stop(key,result.get("stop_reason") or "事実不明",six)
    desk=workspace.desk()
    if not desk["queue"] or desk["queue"][0]["id"]!=queued["id"] or desk["queue"][0]["kind"]!="停止案件":
        raise AssertionError("Threads P3 stop is not top of president desk")
    print(json.dumps({
        "Threads01_P3_result":"A",
        "material":material,
        "employee_output":None,
        "stop_reason":result.get("stop_reason"),
        "stop_stage":result.get("stop_stage"),
        "missing_or_unknown":six["不足・不明点"],
        "question_for_coco":six["Cocoへの質問"],
        "publish":"not called",
        "x_06":"not called",
        "E567":"not called",
    },ensure_ascii=False))
else:
    body=result["state"]["candidates"]["A"]["fields"].get("content","")
    print(json.dumps({
        "Threads01_P3_result":"employee_completed_needs_Coco_comparison",
        "material":material,
        "employee_output":body,
        "facts_used":result.get("facts_used",[]),
        "completion_check":result.get("completion_check"),
        "vp_gate":"not tested; no independent AI VP reviewer exists in this harness",
        "publish":"not called",
        "x_06":"not called",
        "E567":"not called",
    },ensure_ascii=False))

tmp.cleanup()
