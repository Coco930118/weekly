import {request,node,setToken,loadPosts,loadState,filterPosts} from './data.mjs';
import {showStatus} from './status.mjs';
import {showEditor,showHistory} from './editor.mjs';
import {showLogs} from './generation.mjs';
const $=id=>document.getElementById(id);let posts=[];let state;
function error(e){$('message').textContent=e.message;if(e.current){const panel=node('pre','競合：入力欄は保存前の変更を維持しています。\n現在の保存版：\n'+JSON.stringify(e.current,null,2));$('editor').append(panel);}}
async function display(next){state=next;$('message').textContent='';showEditor($('editor'),state,display,error);const source=node('details');source.append(node('summary','weekly正本の読取表示'),node('pre',JSON.stringify(posts.find(p=>p.key===state.key)?.source,null,2)));$('editor').append(source);await showHistory($('history'),state,display,error);await showLogs(state.key,$('logs'));}
function filter(){const list=filterPosts(posts,$('week').value,$('platform').value);$('post').replaceChildren(...list.map(p=>node('option',`${p.platform}｜${p.label}`,{value:p.key})));}
$('load').onclick=async()=>{try{if($('post').value)await display(await loadState($('post').value));}catch(e){error(e);}};
$('week').onchange=filter;$('platform').onchange=filter;
$('auth').onclick=()=>{const value=prompt('サーバー側に設定したCoco操作tokenを入力してください。ブラウザには永続保存しません。');if(value!==null)setToken(value);};
try {
 const [employees,workflow,rows]=await Promise.all([request('/atelier/config/employees.json'),request('/atelier/config/workflow.json'),loadPosts()]);posts=rows;
 for(const p of employees){const item=node('details');item.append(node('summary',`ID${p.id} ${p.name}`),node('p',p.role));$('employees').append(item);}
 $('workflow').append(...workflow.stages.map(s=>node('span',s.name)));
 for(const week of [...new Set(posts.map(p=>p.week))].filter(Boolean))$('week').append(node('option',week,{value:week}));
 for(const platform of [...new Set(posts.map(p=>p.platform))])$('platform').append(node('option',platform,{value:platform}));
 filter();await showStatus($('status'));if($('post').value)await display(await loadState($('post').value));
}catch(e){error(e);}
