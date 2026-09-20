#!/usr/bin/env python3
import glob, json
changed=[]
for path in glob.glob('posts/*.json'):
    try:
        with open(path, encoding='utf-8') as f:
            data=json.load(f)
    except Exception:
        continue
    dirty=False
    for post in data.get('posts', []):
        if post.get('final_editor_status') == 'pending_check':
            post['final_editor_status']='public_ok'
            dirty=True
    if dirty:
        with open(path,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2)
            f.write('\n')
        changed.append(path)
print('public_ok:', ', '.join(changed) if changed else 'none')
