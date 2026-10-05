import {loadDesk,node,resolveSecretary,routeStopToProposal,decideProposal} from './data.mjs';

function groupRows(rows,key){
 const map=new Map();for(const row of rows){const k=row[key]||'未分類';if(!map.has(k))map.set(k,[]);map.get(k).push(row);}return map;
}
function top(){window.scrollTo({top:0,left:0,behavior:'auto'});}
function field(label,value){const row=node('div');row.className='desk-field';row.append(node('span',label),node('strong',String(value??'')));return row;}
function emptyMessage(container,text){const p=node('p',text);p.className='desk-empty';container.append(p);}
function refresh(container){return showDesk(container).then(top);}

export async function showDesk(container){
 const data=await loadDesk();container.replaceChildren();
 const queue=data.queue||[];
 const stops=queue.filter(x=>x.kind==='停止案件');
 const proposals=queue.filter(x=>x.kind==='仕組み提案');

 const header=node('div');header.className='desk-heading';
 header.append(node('h2','社長の机'),node('p',!stops.length&&!proposals.length?'今日は何もありません。':'判断が必要なものだけ上から並んでいます。'));
 container.append(header);

 const stop=node('section');stop.className='desk-block stops';stop.dataset.section='stops';
 stop.append(node('h2',`停止中（${stops.length}）`));
 if(!stops.length)emptyMessage(stop,'停止なし');
 for(const row of stops){
   const p=row.payload||{};const card=node('article');card.className='stop-card';card.dataset.queueId=row.id;
   card.append(
     field('部門',row.department),
     field('投稿番号',p['投稿番号']||row.key||''),
     field('停止工程',p['停止工程']||row.stage||''),
     field('不足内容',p['不足・不明点']||''),
     field('Cocoへの質問',p['Cocoへの質問']||'')
   );
   const facts=node('details');facts.className='confirmed-facts';facts.append(node('summary','確認済みの事実'),node('p',p['現在確認できる事実']||''));card.append(facts);
   const actions=node('div');actions.className='stop-actions';
   const answer=node('button','回答する');answer.dataset.action='answer';
   answer.onclick=()=>{let form=card.querySelector('.answer-form');if(form){form.remove();answer.textContent='回答する';return;}
     form=node('form');form.className='answer-form';const input=node('textarea',undefined,{placeholder:'Cocoの回答',rows:3});input.setAttribute('aria-label','Cocoの回答');
     const send=node('button','送信',{type:'submit'});form.append(input,send);form.onsubmit=async e=>{e.preventDefault();if(!input.value.trim())return;await resolveSecretary(row.id,input.value.trim());await refresh(container);};card.append(form);input.focus();answer.textContent='回答を閉じる';};
   const proceed=node('button','このまま進める');proceed.dataset.action='proceed';proceed.onclick=async()=>{await resolveSecretary(row.id,'このまま進める');await refresh(container);};
   const proposal=node('button','仕組み提案へ回す');proposal.dataset.action='proposal';proposal.onclick=async()=>{await routeStopToProposal(row.id);await refresh(container);};
   actions.append(answer,proceed,proposal);card.append(actions);stop.append(card);
 }
 container.append(stop);

 const proposalsBlock=node('section');proposalsBlock.className='desk-block proposals';proposalsBlock.dataset.section='proposals';
 proposalsBlock.append(node('h2',`確認待ち（${proposals.length}）`));
 if(!proposals.length)emptyMessage(proposalsBlock,'確認待ちなし');
 for(const row of proposals){
   const p=row.payload||{};const card=node('article');card.className='proposal-card';card.dataset.queueId=row.id;
   card.append(field('現象',p['現象']),field('回数',p['回数']),field('原因工程',p['原因工程']),field('変更案',p['変更案']),field('影響範囲',p['影響範囲']));
   const actions=node('div');actions.className='proposal-actions';
   const approve=node('button','承認');approve.onclick=async()=>{await decideProposal(row.id,'承認');await refresh(container);};
   const reject=node('button','却下');reject.onclick=async()=>{await decideProposal(row.id,'却下');await refresh(container);};
   actions.append(approve,reject);card.append(actions);proposalsBlock.append(card);
 }
 container.append(proposalsBlock);

 const completed=node('section');completed.className='desk-block completed';completed.dataset.section='completed';
 completed.append(node('h2',`完成投稿（${(data.completed||[]).length}）`));
 const groups=groupRows(data.completed||[],'department');
 for(const department of ['X','Threads','X短文']){
   const section=node('details');section.className='completed-group';section.open=true;const rows=groups.get(department)||[];
   section.append(node('summary',`${department}（${rows.length}）`));
   if(!rows.length)emptyMessage(section,'なし');
   for(const row of rows){const a=node('button',`${row.label||row.key} を開く`);a.className='completed-link';a.dataset.key=row.key;a.dataset.department=department;
     a.onclick=()=>document.dispatchEvent(new CustomEvent('atelier:open-post',{detail:{key:row.key,department}}));section.append(a);}
   completed.append(section);
 }
 container.append(completed);

 const records=node('details');records.className='desk-block records';records.dataset.section='records';records.open=false;records.append(node('summary','裏側の記録'));
 const rankings=data.audit?.rankings||[];
 for(const department of ['X','Threads','X短文']){
   const rows=rankings.filter(r=>r.department===department);records.append(node('h3',`${department} 修正ランキング`));
   const table=node('table');table.className='audit-table';const head=node('tr');['修正理由','回数','直近発生日','ルール変更候補'].forEach(x=>head.append(node('th',x)));table.append(head);
   if(!rows.length){const tr=node('tr');const td=node('td','記録なし');td.colSpan=4;tr.append(td);table.append(tr);}
   for(const row of rows){const tr=node('tr');tr.append(node('td',row.reason),node('td',row.count),node('td',row.last_at||''),node('td',row.rule_change_candidate?'候補':'—'));table.append(tr);}
   records.append(table);
 }
 const exceptions=data.audit?.exception_summary||[];
 records.append(node('h3','例外通過'));
 for(const department of ['X','Threads','X短文']){
   const rows=exceptions.filter(r=>r.department===department);const block=node('div');block.className='exception-group';block.append(node('h4',department));
   if(!rows.length)block.append(node('p','記録なし'));for(const row of rows)block.append(node('p',`${row.direction}｜${row.count}回｜直近 ${row.last_at||''}`));records.append(block);
 }
 records.append(node('h3','ルール変更履歴'));
 const history=data.audit?.rule_changes||[];if(!history.length)records.append(node('p','記録なし'));
 for(const row of history){const article=node('article');article.className='rule-history';article.append(
   field('旧',row.old_rule),field('新',row.new_rule),field('理由',row.reason),field('承認',row.coco_approval),
   field('承認日',row.approval_date),field('適用開始',row.effective_from),field('影響範囲',row.impact)
 );records.append(article);}
 container.append(records);
}
