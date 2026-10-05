import {loadDesk,node} from './data.mjs';
function groupRows(rows,key){
 const map=new Map();for(const row of rows){const k=row[key]||'未分類';if(!map.has(k))map.set(k,[]);map.get(k).push(row);}return map;
}
export async function showDesk(container){
 const data=await loadDesk();container.replaceChildren();
 const stop=node('section');stop.className='desk-block urgent';stop.append(node('h2',`停止中（${data.stops.length}）`));
 if(!data.stops.length)stop.append(node('p','Cocoの回答待ちはありません。'));
 for(const row of data.stops){const card=node('article');card.append(node('strong',`${row.department}｜${row.key}｜${row.stage}`),node('p',row.issue),node('p',`Cocoへの質問：${row.question}`));stop.append(card);}
 const proposals=node('section');proposals.className='desk-block';proposals.append(node('h2',`Coco確認待ち（${data.proposals.length}）`));
 if(!data.proposals.length)proposals.append(node('p','仕組み変更の確認待ちはありません。'));
 for(const row of data.proposals){const card=node('article');card.append(node('strong',`${row.department}｜${row.phenomenon}（${row.occurrence_count}回）`),node('p',`原因工程：${row.cause_stage}`),node('p',`変更案：${row.proposal}`),node('p',`影響範囲：${row.impact}`));proposals.append(card);}
 const completed=node('section');completed.className='desk-block';completed.append(node('h2',`完成投稿（${data.completed.length}）`));
 if(!data.completed.length)completed.append(node('p','Coco採用済みの作業投稿はまだありません。'));
 for(const row of data.completed.slice(0,30))completed.append(node('p',`${row.platform}｜${row.key}｜候補${row.adopted}`));
 const records=node('details');records.className='desk-block';records.append(node('summary','裏側の記録'));
 const rankings=data.audit.rankings||[];for(const [department,rows] of groupRows(rankings,'department')){records.append(node('h3',`${department} 修正ランキング`));if(!rows.length)records.append(node('p','記録なし'));for(const row of rows){records.append(node('p',`${row.reason}｜${row.count}回｜直近 ${row.last_at}${row.rule_change_candidate?'｜ルール変更候補':''}`));}}
 records.append(node('h3','Coco判断で例外通過'),node('pre',JSON.stringify(data.audit.exceptions||[],null,2)),node('h3','ルール変更履歴'),node('pre',JSON.stringify(data.audit.rule_changes||[],null,2)));
 container.append(stop,proposals,completed,records);
}
