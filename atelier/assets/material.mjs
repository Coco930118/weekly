import {node,loadMaterialPending,materialStart,materialAnswer,materialPropose,materialSelect,materialGeneralizePreview,materialFinalize} from './data.mjs';

// キー名は atelier/canon/interview.md が正典。ここは表示用の複製。
const GATE_FIELDS=['日付','媒体と置き換え先','場面','わたしがしたこと','そのあと起きたこと','【必ず残す事実】3点','対応表','原文'];
const DRAFT_FIELDS=['軸','場面','わたしがしたこと','そのあと起きたこと'];
const DRAFT_OPTIONAL_FIELD='この案で足りない問い';
const LIST_GATE_FIELDS=new Set(['【必ず残す事実】3点','対応表']);
// 「日付」はCocoが原文を打った日時をシステム側で入れる（取材社員には求めない・2026-10-10）。
// 原文中の時期表現は形式ゲートの外、別枠に残す。
const TIME_EXPRESSION_FIELD='原文中の時期の表現';

function field(label,value){const row=node('div');row.className='desk-field';row.append(node('span',label),node('strong',String(value??'')));return row;}
function labeledInput(label,tag='input',attrs={}){const wrap=node('label');wrap.className='material-field';const input=node(tag,undefined,attrs);wrap.append(node('span',label),input);return {wrap,input};}

async function refresh(container){await showMaterialPanel(container);container.scrollIntoView({block:'start',behavior:'auto'});}

// Cocoが打つのは原文・聞き返しへの答え・案の選択・追記だけ。9問を埋める・案を作る・
// 一般化するのは取材社員（Claude）がサーバー側で行う（data.mjsのmaterialStart等）。
function startForm(container,onDone){
  const form=node('form');form.className='material-start-form';
  const caseId=labeledInput('投稿番号（既存の投稿キー）','input',{placeholder:'posts/week_....json#0'});
  const department=labeledInput('部門','select');for(const d of ['X','Threads'])department.input.append(node('option',d,{value:d}));
  const raw=labeledInput('原文（Cocoが話す。整えない）','textarea',{rows:6,placeholder:'実際に何が起きたか、思い出したまま話す。'});
  form.append(caseId.wrap,department.wrap,raw.wrap);
  const submit=node('button','取材社員に渡す',{type:'submit'});form.append(submit);
  form.onsubmit=async e=>{
    e.preventDefault();
    await materialStart(caseId.input.value.trim(),department.input.value,raw.input.value);
    await onDone();
  };
  container.append(form);
}

function missingBlock(card,caseId,missing,onDone){
  if(!missing.length)return;
  const block=node('div');block.className='material-missing';
  block.append(node('p',`取材社員が9問を埋めたところ、足りない項目（${missing.length}）：${missing.join('／')}`));
  const form=node('form');const inputs=missing.map(p=>labeledInput(p,'input'));form.append(...inputs.map(i=>i.wrap));
  const submit=node('button','回答する',{type:'submit'});form.append(submit);
  form.onsubmit=async e=>{e.preventDefault();const answers={};missing.forEach((p,i)=>{answers[p]=inputs[i].input.value;});await materialAnswer(caseId,answers);await onDone();};
  block.append(form);card.append(block);
}

function draftsBlock(card,caseId,row,onDone){
  const block=node('div');block.className='material-drafts';
  if(!row.drafts){
    block.append(node('p','9問は揃いました。素材案（最大3つ）を取材社員に作ってもらう。'));
    const make=node('button','取材社員に案を作ってもらう');
    make.onclick=async()=>{await materialPropose(caseId);await onDone();};
    block.append(make);
  }else if(!row.selected_option){
    block.append(node('p','取材社員が作った素材案。Cocoが選ぶ。'));
    for(const [i,draft] of row.drafts.entries()){
      const d=node('div');d.className='material-draft-card';
      d.append(...[...DRAFT_FIELDS,DRAFT_OPTIONAL_FIELD].filter(f=>draft[f]).map(f=>field(f,draft[f])));
      const pick=node('button',`案${'ABC'[i]}を選ぶ`);
      pick.onclick=async()=>{await materialSelect(caseId,'ABC'[i],addendumInput.value);await onDone();};
      d.append(pick);block.append(d);
    }
    const none=node('button','案なし・自分で書く');
    const addendumWrap=labeledInput('共通の追記（Cocoの事実として原文と同じ扱い）','textarea',{rows:2});
    var addendumInput=addendumWrap.input;
    none.onclick=async()=>{await materialSelect(caseId,'案なし・自分で書く',addendumInput.value);await onDone();};
    block.append(addendumWrap.wrap,none);
  }else if(!row.public_material){
    block.append(field('選択',row.selected_option));
    if(row.has_addendum)block.append(field('追記','あり'));
    const make=node('button','取材社員に公開用素材を作ってもらう');
    make.onclick=async()=>{
      const preview=await materialGeneralizePreview(caseId);
      finalizeForm(block,caseId,preview,onDone);
      make.remove();
    };
    block.append(make);
  }
  card.append(block);
}

// 取材社員が作った下書きをCocoが直せる形で表示する（点2：それ以外の欄は取材社員が埋め、
// Cocoが直せる）。確定するまでは公開用素材はまだ保存されていない。
function finalizeForm(block,caseId,preview,onDone){
  block.append(node('p','公開用素材の下書き（取材社員作成。直してから確定する・8項目が揃わないと完了しない）'));
  if(preview.smell_flags&&Object.keys(preview.smell_flags).length){
    const warn=node('p');warn.className='material-missing';
    warn.textContent='業種の匂いの印：'+Object.entries(preview.smell_flags).map(([f,ws])=>`${f}（${ws.join('・')}）`).join('／');
    block.append(warn);
  }
  const form=node('form');
  const multiline=f=>f==='原文'||LIST_GATE_FIELDS.has(f);
  const toText=v=>Array.isArray(v)?v.join('\n'):String(v??'');
  const gateInputs=GATE_FIELDS.map(f=>labeledInput(
    f==='日付'?'日付（Cocoが原文を打った日。システム側で入る・確定時に上書きされる）':LIST_GATE_FIELDS.has(f)?`${f}（1行に1つ）`:f,
    multiline(f)?'textarea':'input',
    f==='日付'
      ?{value:toText(preview.public_material?.[f]),readOnly:true}
      :multiline(f)?{rows:3,value:toText(preview.public_material?.[f])}:{value:toText(preview.public_material?.[f])},
  ));
  const timeExpression=labeledInput(
    `${TIME_EXPRESSION_FIELD}（参考・確定ゲートの対象外。原文にあればそのまま）`,'input',
    {value:toText(preview.public_material?.[TIME_EXPRESSION_FIELD])},
  );
  const nextEmployee=labeledInput('渡す投稿社員のID','input',{placeholder:'X01 / T01 等'});
  form.append(...gateInputs.map(i=>i.wrap),timeExpression.wrap,nextEmployee.wrap);
  const submit=node('button','公開用素材を確定する',{type:'submit'});form.append(submit);
  form.onsubmit=async e=>{e.preventDefault();
    const publicMaterial={};
    GATE_FIELDS.forEach((f,i)=>{
      const value=gateInputs[i].input.value;
      publicMaterial[f]=LIST_GATE_FIELDS.has(f)?value.split('\n').map(x=>x.trim()).filter(Boolean):value;
    });
    publicMaterial[TIME_EXPRESSION_FIELD]=timeExpression.input.value;
    const result=await materialFinalize(caseId,publicMaterial,nextEmployee.input.value.trim()||undefined);
    if(!result.complete){alert('工程未完了：'+result.missing.join('／'));}
    await onDone();
  };
  block.append(form);
}

export async function showMaterialPanel(container){
  const rows=await loadMaterialPending();
  container.replaceChildren();
  const header=node('div');header.className='material-heading';
  header.append(node('h2','素材を話す'),node('p','Cocoが打つのは原文・聞き返しへの答え・案の選択・追記だけ。9問を埋める・素材案を作る・一般化するのは取材社員（Claude）。2回聞いても1・3・6が埋まらなければ課長へ。'));
  container.append(header);
  for(const row of rows){
    const card=node('article');card.className='material-card';card.dataset.caseId=row.case_id;
    card.append(field('投稿番号',row.case_id),field('部門',row.department),field('聞き返し回数',row.follow_up_count));
    const onDone=()=>refresh(container);
    missingBlock(card,row.case_id,row.missing_points||[],onDone);
    if(!(row.missing_points||[]).length)draftsBlock(card,row.case_id,row,onDone);
    container.append(card);
  }
  const startSection=node('section');startSection.className='material-start';
  startSection.append(node('h3','新しい素材を話す'));
  startForm(startSection,()=>refresh(container));
  container.append(startSection);
}
