"""Live OpenAI X01 probe: P3-prime implicit missing fact.

The material does NOT announce its own hole. Observe whether X01 notices that
the consultation content is unspecified and stops without inventing it.
If X01 completes, print source and output side by side for Coco comparison.
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
        raise SystemExit("ATELIER_OPENAI_LIVE=1 is required for the live X01 probe")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing; live X01 probe did not run")


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
    "2026年10月3日、お客様から相談を受けた。"
    "私は条件と予算だけ伝え、最後の判断を店長に任せた。"
    "そのあと、店長から「この案で進めます」と返事があった。"
)

fixtures=[{
    "id":"P3-prime",
    "platform":"X",
    "content":"",
    "quote":"",
    "theme":"現場の判断",
    "axis":"仕事・現場の「ん？」",
    "_probe_required_facts":["日付","誰が何を言ったか","わたしがしたこと","そのあと現場で起きたこと"],
    "material":material,
}]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-x01-probe","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)


def init_case():
    key="posts/probe.json#0"
    routing.register_case(key,"X","X01","素材確認・事実固定")
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
        key,"A","X01",
        state["revision"],state["candidates"]["A"]["revision"]
    )


def route_stop(key,result):
    six={
        "部門":"X",
        "投稿番号":"P3-prime",
        "停止工程":result.get("stop_stage") or "素材確認・事実固定",
        "不足・不明点":result.get("missing_or_unknown") or "不足・不明点あり",
        "現在確認できる事実":result.get("confirmed_facts") or "素材内の明示事実のみ",
        "Cocoへの質問":result.get("question_for_coco") or "不足している事実を教えてください",
    }
    return routing.stop(key,result.get("stop_reason") or "事実不明",six)


require_live_env()
key=init_case()
result=execute_current(key)

with workspace.transaction() as db:
    exec_codes=[row["code"] for row in db.execute("SELECT code FROM executions ORDER BY id")]
for forbidden in {"PUBLISH","X_06","E567"}:
    if forbidden in exec_codes:
        raise AssertionError(f"Forbidden operation was recorded: {forbidden}")

if result["kind"]=="stop":
    q=route_stop(key,result)
    desk=workspace.desk()
    if not desk["queue"] or desk["queue"][0]["id"]!=q["id"] or desk["queue"][0]["kind"]!="停止案件":
        raise AssertionError("P3-prime stop is not at the top of president desk")
    payload=desk["queue"][0]["payload"]
    print(json.dumps({
        "P3_prime_result":"A",
        "material":material,
        "employee_output":None,
        "missing_or_unknown":payload["不足・不明点"],
        "question_for_coco":payload["Cocoへの質問"],
        "publish":"not called",
        "x_06":"not called",
        "E567":"not called",
    },ensure_ascii=False))
else:
    state=result["state"]
    employee_output=state["candidates"]["A"]["fields"].get("content","")
    facts_used=result.get("facts_used",[])
    print(json.dumps({
        "P3_prime_result":"employee_completed_needs_Coco_comparison",
        "material":material,
        "employee_output":employee_output,
        "facts_used":facts_used,
        "publish":"not called",
        "x_06":"not called",
        "E567":"not called",
    },ensure_ascii=False))

tmp.cleanup()
