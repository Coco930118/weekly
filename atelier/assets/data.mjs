let token = '';
export function setToken(value) { token = value; }
export async function request(path, data) {
  const response = await fetch(path, data ? {method:'POST', headers:{'Content-Type':'application/json', Authorization:`Bearer ${token}`}, body:JSON.stringify(data)} : {});
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.message || result.error); error.code=result.error; error.current=result.current; throw error; }
  return result;
}
export const loadPosts = () => request('/api/posts');
export const loadState = key => request(`/api/state?key=${encodeURIComponent(key)}`);
export const loadHistory = key => request(`/api/history?key=${encodeURIComponent(key)}`);
export const loadLogs = key => request(`/api/logs?key=${encodeURIComponent(key)}`);
export const loadDesk = () => request('/api/desk');
export const loadAudit = () => request('/api/audit');
export const loadMaterialPending = (department) => request(`/api/material/pending${department?`?department=${encodeURIComponent(department)}`:''}`);
export const loadMaterialSummary = (caseId) => request(`/api/material/summary?key=${encodeURIComponent(caseId)}`);
export const materialStart = (caseId,department,employee,rawMaterial,points) => request('/api/material/start',{case_id:caseId,department,employee,raw_material:rawMaterial,points});
export const materialAnswer = (caseId,answers) => request('/api/material/answer',{case_id:caseId,answers});
export const materialPropose = (caseId,drafts) => request('/api/material/propose',{case_id:caseId,drafts});
export const materialSelect = (caseId,selection,addendum) => request('/api/material/select',{case_id:caseId,selection,addendum});
export const materialFinalize = (caseId,publicMaterial,nextEmployee) => request('/api/material/finalize',{case_id:caseId,public_material:publicMaterial,next_employee:nextEmployee});
export const recordException = (key,note) => request('/api/exception',{key,note});
export const resolveSecretary = (id,response) => request('/api/secretary/resolve',{id,response});
export const routeStopToProposal = id => request('/api/secretary/route-proposal',{id});
export const decideProposal = (id,decision) => request('/api/secretary/decision',{id,decision});
export const mutate = (state, action, payload) => request('/api/mutate', {key:state.key,revision:state.revision,action,payload});
export function node(tag, text, attrs={}) { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; Object.assign(e,attrs); return e; }
export function filterPosts(posts,week,platform) { return posts.filter(p=>(!week || p.week===week)&&(!platform || p.platform===platform)); }
