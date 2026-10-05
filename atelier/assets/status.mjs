import {request,node} from './data.mjs';
export async function showStatus(container) {
 const s=await request('/api/status');
 container.replaceChildren(node('p',`AI：${s.ai} ／ 公開処理：${s.publish} ／ 保存先：${s.db} ／ 編集：${s.write_enabled?'認証後に可能':'操作token未設定'}`));
}
