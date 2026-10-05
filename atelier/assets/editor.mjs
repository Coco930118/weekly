import {node,mutate,loadHistory,request} from './data.mjs';
import {generationStatus} from './generation.mjs';
export function previewDiff(before,after) {
 return Object.keys({...before,...after}).filter(k=>JSON.stringify(before[k])!==JSON.stringify(after[k])).map(k=>`${k}\n− ${JSON.stringify(before[k])}\n＋ ${JSON.stringify(after[k])}`).join('\n\n') || '変更なし';
}
export function showEditor(container,state,onSave,onError) {
 container.replaceChildren();container.append(node('h2',`投稿revision ${state.revision} ／ Atelier：${state.status} ／ weekly public_ok：${JSON.stringify(state.source_public_ok)}`), generationStatus());
 const theme=node('input',undefined,{value:state.theme,placeholder:'投稿のtheme'}),axis=node('input',undefined,{value:state.axis,placeholder:'投稿のaxis'});
 const basis=node('div');basis.className='basis';basis.append(node('label','theme'),theme,node('label','axis'),axis);
 const basisPreview=node('pre','');const basisButton=node('button','基準値のdiffを確認');
 basisButton.onclick=()=>{basisPreview.textContent=previewDiff({theme:state.theme,axis:state.axis},{theme:theme.value,axis:axis.value});};
 const saveBasis=node('button','Cocoの基準値を保存');saveBasis.onclick=async()=>{if(!confirm(`${previewDiff({theme:state.theme,axis:state.axis},{theme:theme.value,axis:axis.value})}\nレビュー・採用状態は再確認対象になります。`))return;try{await onSave(await mutate(state,'basis',{theme:theme.value,axis:axis.value}));}catch(e){onError(e);}};
 basis.append(basisButton,saveBasis,basisPreview);container.append(basis);
 if(state.needs_split)container.append(node('pre',`NEEDS_SPLIT：${state.needs_split.split_at}\n自動リライトは行いません。Cocoが投稿の基準を確認してください。`));
 const grid=node('div');grid.className='candidates';container.append(grid);
 for(const [name,candidate] of Object.entries(state.candidates)) {
  const card=node('article');card.append(node('h3',`候補${name}｜${({A:'いつもの構成',B:'澄んだ短文',C:'Cocoのぼやき / 統合案'})[name]} ／ revision ${candidate.revision}${state.adopted===name?' ／ 採用済み':''}`));const inputs={};
  for(const [field,value] of Object.entries(candidate.fields)) {
   card.append(node('label',`${field}${candidate.protected[field]?' ／ Coco修正保護':''}`));
   const input=node('textarea',undefined,{value:typeof value==='string'?value:JSON.stringify(value,null,2)});inputs[field]=input;card.append(input);
  }
  function values(){return Object.fromEntries(Object.entries(inputs).map(([f,e])=>[f,typeof candidate.fields[f]==='string'?e.value:JSON.parse(e.value)]));}
  const diff=node('pre','');const preview=node('button','diff確認');preview.onclick=()=>{try{diff.textContent=previewDiff(candidate.fields,values());}catch(e){onError(e);}};
  const save=node('button','直接編集を保存');save.onclick=async()=>{try{const fields=values();diff.textContent=previewDiff(candidate.fields,fields);if(!confirm(diff.textContent+'\n作業DBへ保存しますか？'))return;await onSave(await mutate(state,'edit',{candidate:name,candidate_revision:candidate.revision,fields}));}catch(e){onError(e);}};
  const adopt=node('button','Coco採用');adopt.onclick=async()=>{try{if(previewDiff(candidate.fields,values())!=='変更なし')throw new Error('直接編集を保存してから採用してください');await onSave(await mutate(state,'adopt',{candidate:name,candidate_revision:candidate.revision}));}catch(e){onError(e);}};
  card.append(preview,save,adopt,diff);grid.append(card);
 }
 container.append(node('h3','Coco確認待ちの提案diff'),node('pre',JSON.stringify(state.proposals||[],null,2)));
 container.append(node('h3','レビュー'),node('pre',JSON.stringify(state.reviews,null,2)));
}
export async function showHistory(container,state,onSave,onError) {
 const history=await loadHistory(state.key);container.replaceChildren();
 function restoreButton(target,section) {
  const button=node('button',`revision ${target}への復元diffを確認`);
  button.onclick=async()=>{try{
   const preview=await request(`/api/revert-preview?key=${encodeURIComponent(state.key)}&revision=${target}`);
   const diff=node('pre',JSON.stringify(preview.diff,null,2));const apply=node('button','このdiffで復元');
   apply.onclick=async()=>{try{await onSave(await mutate({...state,revision:preview.revision},'revert',{target_revision:target}));}catch(e){onError(e);}};
   section.append(diff,apply);button.disabled=true;
  }catch(e){onError(e);}};return button;
 }
 for(const item of history){const section=node('details');section.append(node('summary',`revision ${item.revision} ／ ${item.actor} ／ ${item.action} ／ ${item.at}`),node('pre',JSON.stringify(item.diff,null,2)),restoreButton(item.revision,section));container.append(section);}
 if(history.length)container.append(restoreButton(0,container));
}
