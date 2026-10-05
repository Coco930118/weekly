import {loadDesk,node,resolveSecretary,routeStopToProposal} from './data.mjs';
function groupRows(rows,key){
 const map=new Map();for(const row of rows){const k=row[key]||'未分類';if(!map.has(k))map.set(k,[]);map.get(k).push(row);}return map;
}
export async function showDesk(container){
 const data=await loadDesk();container.replaceChildren();
 const queue=data.queue||[];
 const stops=queue.filter(x=>x.kind==='停止案件');
 const proposals=queue.filter(x=>x.kind==='仕組み提案');

 const stop=node('section');stop.className='desk-block urgent';stop.append(node('h2',`停止中（${stops.length}）`));
 if(!stops.length)stop.append(node('p','Cocoの回答待ちはありません。'));
 for(const row of stops){const p=row.payload||{};const card=node('article');card.append(
   node('strong',`${row.department}｜${p['投稿番号']||row.key||''}｜${p['停止工程']||row.stage||''}`),
   node('p',p['不足・不明点']||''),
   node('p',`確認済みの事実：${p['現在確認できる事実']||''}`),
   node('p',`Cocoへの質問：${p['Cocoへの質問']||''}`)
 );
 const answer=node('button','回答する');answer.onclick=async()=>{const value=prompt('Cocoの回答を入力してください。');if(value&&value.trim()){await resolveSecretary(row.id,value.trim());await showDesk(container);}};
 const proceed=node('button','このまま進める');proceed.onclick=async()=>{await resolveSecretary(row.id,'このまま進める');await showDesk(container);};
 const proposal=node('button','仕組み提案へ回す');proposal.onclick=async()=>{await routeStopToProposal(row.id);await showDesk(container);};
 card.append(answer,proceed,proposal);stop.append(card);}

 const proposalsBlock=node('section');proposalsBlock.className='desk-block';proposalsBlock.append(node('h2',`Coco確認待ち（${proposals.length}）`));
 if(!proposals.length)proposalsBlock.append(node('p','仕組み変更の確認待ちはありません。'));
 for(const row of proposals){const p=row.payload||{};const card=node('article');card.append(
   node('strong',`${row.department}｜${p['現象']||''}（${p['回数']||0}回）`),
   node('p',`原因工程：${p['原因工程']||''}`),
   node('p',`変更案：${p['変更案']||''}`),
   node('p',`影響範囲：${p['影響範囲']||''}`)
 );
 const approve=node('button','承認する');approve.onclick=async()=>{await resolveSecretary(row.id,'承認');await showDesk(container);};
 const reject=node('button','却下する');reject.onclick=async()=>{await resolveSecretary(row.id,'却下');await showDesk(container);};
 card.append(approve,reject);proposalsBlock.append(card);}

 const completed=node('section');completed.className='desk-block';completed.append(node('h2',`完成投稿（${data.completed.length}）`));
 if(!data.completed.length)completed.append(node('p','Coco採用済みの作業投稿はまだありません。'));
 for(const row of data.completed.slice(0,30))completed.append(node('p',`${row.platform}｜${row.key}｜候補${row.adopted}`));

 const records=node('details');records.className='desk-block';records.append(node('summary','裏側の記録'));
 const rankings=data.audit.rankings||[];for(const [department,rows] of groupRows(rankings,'department')){records.append(node('h3',`${department} 修正ランキング`));if(!rows.length)records.append(node('p','記録なし'));for(const row of rows){records.append(node('p',`${row.reason}｜${row.count}回｜直近 ${row.last_at}${row.rule_change_candidate?'｜ルール変更候補':''}`));}}
 records.append(node('h3','Coco判断で例外通過'),node('pre',JSON.stringify(data.audit.exceptions||[],null,2)),node('h3','ルール変更履歴'),node('pre',JSON.stringify(data.audit.rule_changes||[],null,2)));
 container.append(stop,proposalsBlock,completed,records);
}
