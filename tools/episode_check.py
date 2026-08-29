#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E373 素材の週内カウント（全媒体横断）

使い方:  python3 tools/episode_check.py --week 2026-09-01
        python3 tools/episode_check.py --week 2026-09-01 --files posts/week_*.json

【なぜ別ツールか】full_check.py も shindan_check.py も自分のファイルしか読まないため、
**媒体をまたいだ素材の重複は構造的に検出できない**。2026-08-29 のWチェックで、
9/1週の「花」が X診断 9/3 と th_15 9/5 で二重に使われているのが、
3ファイルを手で数えて初めて見つかった。E373 の usage_limit は
「1投稿に1〜2要素まで／同じ要素は週内1回まで」で、週内1回は媒体を問わない。

素材の正典は reference/episodes_soshiki.json の E373（tools/e373.py が読む）。
検出語をこのファイルに書かない。
"""
import json
import glob
import os
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e373

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_KEYS = ('image_prompt', 'image_prompt_full', 'image_prompt_short')


def strings(o, key=None):
    """ネストした中身も含めて、本文になりうる文字列を全部出す。
    リストの中（choices・self_replies など）を取りこぼさないこと。"""
    if isinstance(o, str):
        if key not in SKIP_KEYS:
            yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from strings(v, k)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v, key)


def week_files(week_start):
    """週の頭の日付から、その週の3ファイルを集める。
    35投稿は week_YYYY_MM_DD_*.json、診断は shindan_[x|th]_YYYY-MM-DD.json"""
    u = week_start.replace('-', '_')
    pats = [f'posts/week_{u}_*.json',
            f'posts/shindan_x_{week_start}.json',
            f'posts/shindan_th_{week_start}.json']
    out = []
    for p in pats:
        out += sorted(glob.glob(os.path.join(ROOT, p)))
    return out


def main(files):
    els = e373.elements()
    if not els:
        print('E373 の elements が読めない。reference/episodes_soshiki.json を確認')
        return 1
    if not files:
        print('対象ファイルが見つからない')
        return 1

    hits = collections.defaultdict(list)
    for f in files:
        label = os.path.basename(f)
        try:
            d = json.load(open(f, encoding='utf-8'))
        except (OSError, ValueError) as e:
            print(f'  読めない: {f} ({e})')
            return 1
        for p in d.get('posts', []):
            pid = p.get('id') or p.get('date')
            body = ' '.join(strings(p))
            for e in els:
                if e in body:
                    hits[e].append(f'{label}:{pid}')

    print('=== E373 素材の週内カウント（全媒体横断）===')
    for f in files:
        print(f'  対象: {os.path.relpath(f, ROOT)}')
    print()

    over = {e: v for e, v in hits.items() if len(v) > 1}
    for e in els:
        if e in hits:
            v = hits[e]
            mark = '  ★週内2回以上' if len(v) > 1 else ''
            print(f'  {e:10} {len(v)}回 {v}{mark}')

    print()
    if over:
        print(f'■ 要修正: {len(over)}件（E373 usage_limit「同じ要素は週内1回まで」に抵触）')
        for e, v in over.items():
            print(f'  - {e}: {v}')
    else:
        print('■ 要修正: 0件')

    unused = [e for e in els if e not in hits]
    print(f'\n■ この週で未使用の要素（差し替えに使える）\n  {" ／ ".join(unused) if unused else "（なし）"}')

    print('\n' + '=' * 60)
    print('【判断チェック】機械では判定できない。必ず目視で埋めること')
    print('=' * 60)
    print('① 素材の線引き — わたしの習慣の形（「わたしは〜してる」「〜する。」）で書いた一行は、')
    print('   E373 の要素だけで書けているか。ゼロ主語の軽い一行は E373 に限らない')
    print('   （2026-08-29 Coco決定・恒久ルール）')
    print('② 佇まい枠の episode_id が E373 になっているか（佇まい枠の素材は E373）')
    print('③ 同じ要素が前週と続いていないか（週内1回は機械が見る。週またぎは目視）')
    return 1 if over else 0


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == '--week':
        if len(a) < 2:
            sys.exit('--week には週の頭の日付を渡す（例: --week 2026-09-01）')
        fs = week_files(a[1])
    elif a[0] == '--files':
        fs = [f for pat in a[1:] for f in sorted(glob.glob(pat))]
    else:
        fs = [f for pat in a for f in sorted(glob.glob(pat))]
    sys.exit(main(fs))
