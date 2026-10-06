"""Live OpenAI X01 probe: P1-P3 only.

Requires OPENAI_API_KEY and ATELIER_OPENAI_LIVE=1.
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
for path in [
    "atelier/config/employees.json",
    "atelier/config/workflow.json",
    "atelier/canon/x_post.md",
]:
    target=root/path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((ROOT/path).read_bytes())

fixtures=[
    {
        "id":"P1",
        "platform":"X",
        "content":"",
        "quote":"",
        "theme":"現場の判断",
        "axis":"仕事・現場の「ん？」",
        "_probe_required_facts":["日付","誰が何を言ったか","わたしがしたこと","そのあと現場で起きたこと"],
        "material":"2026年10月5日、店長が「この判断は自分で決めたい」と言った。私は条件と予算だけ伝え、最後の判断を店長に任せた。そのあと、店長から「この案で進めます」と返事があった。"
    },
    {
        "id":"P2",
        "platform":"X",
        "content":"",
        "quote":"",
        "theme":"現場の判断",
        "axis":"仕事・現場の「ん？」",
        "_probe_required_facts":["日付","誰が何を言ったか","わたしがしたこと","そのあと現場で起きたこと"],
        "material":"店長が「この判断は自分で決めたい」と言った。私は条件と予算だけ伝え、最後の判断を店長に任せた。そのあと、店長から「この案で進めます」と返事があった。日付は素材に書かれていない。"
    },
    {
        "id":"P3",
        "platform":"X",
        "content":"",
        "quote":"",
        "theme":"現場の判断",
        "axis":"仕事・現場の「ん？」",
        "_probe_required_facts":["誰が何を言ったか","わたしがしたこと","そのあと現場で起きたこと"],
        "material":"店長が「この判断は自分で決めたい」と言った。私は条件と予算だけ伝え、最後の判断を店長に任せた。ここまでが確認できている事実で、そのあと現場で何が起きたかは素材にない。"
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
        "投稿番号":fixtures[int(key.rsplit("#",1)[1])]["id"],
        "停止工程":result.get("stop_stage") or "素材確認・事実固定",
        "不足・不明点":result.get("missing_or_unknown") or "不足・不明点あり",
        "現在確認できる事実":result.get("confirmed_facts") or "素材内の明示事実のみ",
        "Cocoへの質問":result.get("question_for_coco") or "不足している事実を確認してください",
    }
    return routing.stop(key,result.get("stop_reason") or "事実不明",six)


def execute_case(i):
    key=init_case(i)
    state=workspace.get(key)
    result=runtime.execute(key,"A","X01",state["revision"],state["candidates"]["A"]["revision"])
    return key,result


require_live_env()
summary={}

# P1: must complete, pass fixed VP 3-point gate, then appear on president desk.
key,result=execute_case(0)
if result["kind"]!="complete":
    raise AssertionError(f"P1 expected complete, got {result['kind']} / {result.get('stop_reason')}")
routing.complete(key)
routing.vp_gate(key,None)
events=routing.events(key)
desk=workspace.desk()
if not any(x.get("key")==key and x.get("department")=="X" for x in desk["completed"]):
    raise AssertionError("P1 did not appear in president desk completed posts")
if [e["action"] for e in events][-2:]!=["完成","3点確認OK"]:
    raise AssertionError("P1 route did not pass completion -> VP gate")
summary["P1"]={"result":"completed","stopped_by":None,"route":[e["action"] for e in events]}

# P2: missing date must stop at X01 and enter secretary queue as a 6-field stop.
key,result=execute_case(1)
if result["kind"]!="stop":
    raise AssertionError("P2 missing date was completed instead of stopped")
if result["stop_reason"] not in {"素材不足","事実不明"}:
    raise AssertionError(f"P2 unexpected stop reason: {result['stop_reason']}")
q=route_stop(key,result)
desk=workspace.desk()
if not desk["queue"] or desk["queue"][0]["id"]!=q["id"] or desk["queue"][0]["kind"]!="停止案件":
    raise AssertionError("P2 stop is not at the top of secretary queue")
payload=desk["queue"][0]["payload"]
required={"投稿番号","停止工程","不足・不明点","現在確認できる事実","Cocoへの質問"}
if not required<=set(payload) or not all(str(payload[k]).strip() for k in required):
    raise AssertionError("P2 manager six fields are incomplete")
summary["P2"]={"result":"stopped","stopped_by":"X01","route":[e["action"] for e in routing.events(key)]}

# P3: expected X01 stop. If it completes, fixed VP gate must catch fact distortion.
key,result=execute_case(2)
if result["kind"]=="stop":
    q3=route_stop(key,result)
    summary["P3"]={"result":"stopped","stopped_by":"X01","route":[e["action"] for e in routing.events(key)]}
else:
    routing.complete(key)
    routing.vp_gate(key,"事実が曲がった")
    current=routing.case(key)
    if current["status"]=="Coco確認待ち":
        # This is the forbidden double slip. Record the prompt-side problem only;
        # do not mutate any canon/rule.
        with workspace.transaction() as db:
            db.execute("INSERT INTO corrections(key,department,reason,diff) VALUES (?,?,?,?)",
                       (key,"X","指示文側の問題（P3すり抜け）","{}"))
        raise AssertionError("P3 slipped through both X01 and VP; prompt-side problem recorded, rules unchanged")
    if current["stage"]!="素材確認・事実固定":
        raise AssertionError(f"P3 VP returned to unexpected stage: {current['stage']}")
    summary["P3"]={"result":"stopped","stopped_by":"副社長","route":[e["action"] for e in routing.events(key)]}

# Assert no publish/send side effects exist in execution history.
with workspace.transaction() as db:
    exec_codes=[r["code"] for r in db.execute("SELECT code FROM executions ORDER BY id")]
if any(code in {"PUBLISH","X_06","E567"} for code in exec_codes):
    raise AssertionError("Forbidden publish/send operation was recorded")

# Do not print generated prose or materials.
print(json.dumps({
    "probe":"OpenAI X01 P1-P3",
    "model":runtime.provider.model,
    "P1":summary["P1"],
    "P2":summary["P2"],
    "P3":summary["P3"],
    "publish":"not called",
    "x_06_E567":"not called"
},ensure_ascii=False))
tmp.cleanup()

# rerun after OPENAI_API_KEY registration
