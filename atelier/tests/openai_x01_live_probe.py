"""Live OpenAI X01 probe: P2 stop route only.

Requires OPENAI_API_KEY and ATELIER_OPENAI_LIVE=1.
P2 must stop for missing date, route through manager -> secretary -> president desk.
No publish/x_06/E567 code is called. Generated prose is never printed.
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

fixtures=[
    {
        "id":"P2",
        "platform":"X",
        "content":"",
        "quote":"",
        "theme":"現場の判断",
        "axis":"仕事・現場の「ん？」",
        "_probe_required_facts":["日付","誰が何を言ったか","わたしがしたこと","そのあと現場で起きたこと"],
        "material":"店長が「この判断は自分で決めたい」と言ったあと、「どうしましょう」と最後の判断をこちらに戻してきた。私は条件と予算だけ伝え、最後の判断を店長に任せた。そのあと、店長から「この案で進めます」と返事があった。日付は素材に書かれていない。"
    },
]
(root/"posts/index.json").write_text(json.dumps({"weeks":["probe.json"]}))
(root/"posts/probe.json").write_text(json.dumps({"week":"openai-x01-probe","posts":fixtures},ensure_ascii=False))
(root/"notes/index.json").write_text(json.dumps({"notes":[]}))

workspace=Workspace(root,root/"work.sqlite3")
routing=RoutingEngine(workspace)
runtime=AIRuntime(workspace)


def key_at(i):
    return f"posts/probe.json#{i}"


def init_case(i):
    key=key_at(i)
    routing.register_case(key,"X","X01","素材確認・事実固定")
    state=workspace.get(key)
    if not state["theme"] or not state["axis"]:
        workspace.mutate(key,state["revision"],"basis",{"theme":fixtures[i]["theme"],"axis":fixtures[i]["axis"]})
    return key


def route_stop(key,result):
    six={
        "部門":"X",
        "投稿番号":fixtures[0]["id"],
        "停止工程":result.get("stop_stage") or "素材確認・事実固定",
        "不足・不明点":result.get("missing_or_unknown") or "不足・不明点あり",
        "現在確認できる事実":result.get("confirmed_facts") or "素材内の明示事実のみ",
        "Cocoへの質問":result.get("question_for_coco") or "日付を教えてください",
    }
    return routing.stop(key,result.get("stop_reason") or "事実不明",six), six


def execute_case(i):
    key=init_case(i)
    state=workspace.get(key)
    result=runtime.execute(key,"A","X01",state["revision"],state["candidates"]["A"]["revision"])
    return key,result


require_live_env()
key,result=execute_case(0)
if result["kind"]!="stop":
    raise AssertionError("P2 missing date was completed instead of stopped")
if result["stop_reason"] not in {"素材不足","事実不明"}:
    raise AssertionError(f"P2 unexpected stop reason: {result['stop_reason']}")

q,six=route_stop(key,result)
desk=workspace.desk()
if not desk["queue"]:
    raise AssertionError("P2 stop did not reach president desk")
top=desk["queue"][0]
if top["id"]!=q["id"] or top["kind"]!="停止案件":
    raise AssertionError("P2 stop is not at the top of president desk")
required={"投稿番号","停止工程","不足・不明点","現在確認できる事実","Cocoへの質問"}
payload=top["payload"]
if not required<=set(payload) or not all(str(payload[k]).strip() for k in required):
    raise AssertionError("P2 manager six fields are incomplete")
if "日付" not in payload["Cocoへの質問"]:
    raise AssertionError("P2 Coco question does not ask for the missing date")

print(json.dumps({
    "P2":"stopped",
    "question_for_coco":payload["Cocoへの質問"],
    "six_fields_complete":True,
    "desk_position":"top",
},ensure_ascii=False))
tmp.cleanup()
