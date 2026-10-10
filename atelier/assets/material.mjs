import {node,loadMaterialPending,materialStart,materialAnswer,materialPropose,materialSelect,materialFinalize} from './data.mjs';

// キー名は atelier/canon/interview.md が正典。ここは表示用の複製。
const POINTS=['実際に何が起きたか','誰が何と言ったか','わたしが何をしたか','わたしが何をしなかったか',
  'その前に何があったか','そのあと何が変わったか','何回あったか',
  '数字（人数・時間・金額など、原文にあるものだけ）','まだ決まっていないこと'];
const GATE_FIELDS=['日付','媒体と置き換え先','場面','わたしがしたこと','そのあと起きたこと','【必ず残す事実】3点','対応表','原文'];
const DRAFT_FIELDS=['軸','場面','わたしがしたこと','そのあと起きたこと'];
const DRAFT_OPTIONAL_FIELD='この案で足りない問い';

function field(label,value){const row=node('div');row.className='desk-field';row.append(node('span',label),node('strong',String(value??'')));return row;}
function labeledInput(label,tag='input',attrs={}){const wrap=node('label');wrap.className='material-field';const input=node(tag,undefined,attrs);wrap.append(node('span',label),input);return {wrap,input};}

async function refresh(container){await showMaterialPanel(container);container.scrollIntoView({block:'start',behavior:'auto'});}

function startForm(container,onDone){
  const form=node('form');form.className='material-start-form';
  const caseId=labeledInput('投稿番号（既存の投稿キー）','input',{placeholder:'posts/week_....json#0'});
  const department=labeledInput('部門','select');for(const d of ['X','Threads'])department.input.append(node('option',d,{value:d}));
  const raw=labeledInput('原文（Cocoが話す）','textarea',{rows:6,placeholder:'実際に何が起きたか、思い出したまま話す。'});
  const pointInputs=POINTS.map(p=>labeledInput(p,'input',{placeholder:'（わかれば）'}));
  form.append(caseId.wrap,department.wrap,raw.wrap,...pointInputs.map(p=>p.wrap));
  const submit=node('button','取材社員に渡す',{type:'submit'});form.append(submit);
  form.onsubmit=async e=>{
    e.preventDefault();
    const points={};POINTS.forEach((p,i)=>{points[p]=pointInputs[i].input.value;});
    await materialStart(caseId.input.value.trim(),department.input.value,'MATERIAL',raw.input.value,points);
    await onDone();
  };
  container.append(form);
}

function missingBlock(card,caseId,missing,onDone){
  if(!missing.length)return;
  const block=node('div');block.className='material-missing';
  block.append(node('p',`足りない項目（${missing.length}）：${missing.join('／')}`));
  const form=node('form');const inputs=missing.map(p=>labeledInput(p,'input'));form.append(...inputs.map(i=>i.wrap));
  const submit=node('button','回答する',{type:'submit'});form.append(submit);
  form.onsubmit=async e=>{e.preventDefault();const answers={};missing.forEach((p,i)=>{answers[p]=inputs[i].input.value;});await materialAnswer(caseId,answers);await onDone();};
  block.append(form);card.append(block);
}

function draftsBlock(card,caseId,row,onDone){
  const block=node('div');block.className='material-drafts';
  if(!row.drafts){
    block.append(node('p','素材案（最大3つ。原文にある事実だけで組む。足さない。3つに足りなければ空欄のまま渡す）'));
    const form=node('form');
    const draftInputs=[0,1,2].map(i=>{
      const g=node('fieldset');g.append(node('legend',`案${'ABC'[i]}`));
      const inputs=[...DRAFT_FIELDS,DRAFT_OPTIONAL_FIELD].map(f=>labeledInput(f,'input'));inputs.forEach(x=>g.append(x.wrap));
      block.append(g);return inputs;
    });
    const submit=node('button','素材案を渡す',{type:'submit'});form.append(submit);block.append(form);
    form.onsubmit=async e=>{e.preventDefault();
      const allFields=[...DRAFT_FIELDS,DRAFT_OPTIONAL_FIELD];
      const drafts=draftInputs.map(inputs=>{const d={};allFields.forEach((f,i)=>{if(inputs[i].input.value.trim())d[f]=inputs[i].input.value;});return d;})
        .filter(d=>DRAFT_FIELDS.every(f=>d[f]));
      await materialPropose(caseId,drafts);await onDone();
    };
  }else if(!row.selected_option){
    block.append(node('p','Cocoの選択'));
    for(const [i,draft] of row.drafts.entries()){
      const d=node('div');d.className='material-draft-card';
      d.append(...[...DRAFT_FIELDS,DRAFT_OPTIONAL_FIELD].filter(f=>draft[f]!==undefined).map(f=>field(f,draft[f])));
      const pick=node('button',`案${'ABC'[i]}を選ぶ`);
      pick.onclick=async()=>{await materialSelect(caseId,'ABC'[i],addendumInput.value);await onDone();};
      d.append(pick);block.append(d);
    }
    const none=node('button','案なし・自分で書く');
    const addendumWrap=labeledInput('共通の追記（Cocoの事実として原文と同じ扱い）','textarea',{rows:2});
    var addendumInput=addendumWrap.input;
    none.onclick=async()=>{await materialSelect(caseId,'案なし・自分で書く',addendumInput.value);await onDone();};
    block.append(addendumWrap.wrap,none);
  }else{
    block.append(field('選択',row.selected_option));
    if(row.has_addendum)block.append(field('追記','あり'));
    finalizeForm(block,caseId,onDone);
  }
  card.append(block);
}

const LIST_GATE_FIELDS=new Set(['【必ず残す事実】3点','対応表']);
function finalizeForm(block,caseId,onDone){
  block.append(node('p','公開用素材（出口条件・8項目が揃わないと完了しない）'));
  const form=node('form');
  const multiline=f=>f==='原文'||LIST_GATE_FIELDS.has(f);
  const gateInputs=GATE_FIELDS.map(f=>labeledInput(
    LIST_GATE_FIELDS.has(f)?`${f}（1行に1つ）`:f,
    multiline(f)?'textarea':'input',
    multiline(f)?{rows:3}:{},
  ));
  const nextEmployee=labeledInput('渡す投稿社員のID','input',{placeholder:'X01 / T01 等'});
  form.append(...gateInputs.map(i=>i.wrap),nextEmployee.wrap);
  const submit=node('button','公開用素材を確定する',{type:'submit'});form.append(submit);
  form.onsubmit=async e=>{e.preventDefault();
    const publicMaterial={};
    GATE_FIELDS.forEach((f,i)=>{
      const value=gateInputs[i].input.value;
      publicMaterial[f]=LIST_GATE_FIELDS.has(f)?value.split('\n').map(x=>x.trim()).filter(Boolean):value;
    });
    const result=await materialFinalize(caseId,publicMaterial,nextEmployee.input.value.trim()||undefined);
    if(!result.complete){alert('工程未完了：'+result.missing.join('／'));}
    await onDone();
  };
  block.append(form);
}

export async function showMaterialPanel(container){
  const rows=await loadMaterialPending();
  container.replaceChildren();
  const header=node('div');header.className='desk-heading';
  header.append(node('h2','素材を話す'),node('p','Cocoが原文を打つ欄。9問のうち足りないものだけ、1回3問までで聞き返す（2回聞いても1・3・6が埋まらなければ課長へ）。素材案（最大3つ）→選択・追記→公開用素材の順で投稿社員へ直接渡す。'));
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
