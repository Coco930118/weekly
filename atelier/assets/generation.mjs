import {loadLogs,node} from './data.mjs';
export async function showLogs(key, container) {
 const logs=await loadLogs(key);
 container.textContent=logs.length ? logs.map(l=>`${l.at} ID${l.employee} 候補${l.candidate} ${l.status} ${l.code}`).join('\n') : '実行なし。AI未接続・未有効化。';
}
export function generationStatus() { return node('p','AI未接続。候補のAI生成・素材送信は行いません。'); }
