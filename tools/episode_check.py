#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E373 素材の週内カウント（全媒体横断）

使い方:  python3 tools/episode_check.py --week 2026-09-01
        python3 tools/episode_check.py --week 2026-09-01 --files posts/week_*.json

【なぜ別ツールか】full_check.py・shindan_check.py・note_check.py はどれも自分の
ファイルしか読まないため、**媒体をまたいだ素材の重複は構造的に検出できない**。
2026-08-29 のWチェックで、9/1週の「花」が X診断 9/3 と th_15 9/5 で二重に
使われているのが、手で数えて初めて見つかった。E373 の usage_limit は
「1投稿に1〜2要素まで／同じ要素は週内1回まで」で、週内1回は媒体を問わない。

**対象は 35投稿・診断14本・その週のnote全部**（noteは 2026-08-31 追加）。
noteも媒体なので、生活描写はここで一緒に数える。

素材の正典は reference/episodes_soshiki.json の E373（tools/e373.py が読む）。
**検出語をこのファイルに書かない**（INSERT_RE が持っているのは「〜のも、」という
枠の構文であって、素材の語ではない）。
"""
import json
import glob
import os
import sys
import collections
import re

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
    """週の頭の日付から、その週の全媒体ファイルを集める。
    35投稿は week_YYYY_MM_DD_*.json、診断は shindan_[x|th]_YYYY-MM-DD.json、
    noteは source_week がその週のもの全部。

    **noteを対象に入れたのは 2026-08-31（Coco決定・恒久ルール）。**
    それまで対象は posts/ の3ファイルだけで、noteの生活描写は全媒体横断の
    週内カウントから外れていた。実例：9/1週の note_2026-09-05_invisible に
    「駅のホームでただぼーっとする」があり、これは E373 に無い生活描写だが、
    ツールがそもそも notes/ を開いていないので誰にも検出できなかった。
    E373 の usage_limit「同じ要素は週内1回まで」は媒体を問わない——noteも媒体である。"""
    u = week_start.replace('-', '_')
    pats = [f'posts/week_{u}_*.json',
            f'posts/shindan_x_{week_start}.json',
            f'posts/shindan_th_{week_start}.json']
    out = []
    for p in pats:
        out += sorted(glob.glob(os.path.join(ROOT, p)))
    for f in sorted(glob.glob(os.path.join(ROOT, 'notes', 'note_*.json'))):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if str(d.get('source_week', '')).startswith(week_start):
            out.append(f)
    return out


def items(d, label):
    """ファイルの中身を (id, 本文) の並びにする。
    35投稿・診断は posts[]、noteは1ファイル＝1本。"""
    if 'posts' in d:
        for p in d['posts']:
            yield (p.get('id') or p.get('date')), ' '.join(strings(p))
    else:
        yield label.replace('note_', '').replace('.json', ''), ' '.join(strings(d))


INSERT_RE = re.compile(r'(のも、|のも$|くらいでちょうどいい|くらいがちょうどいい)')


def inserted_lines(md):
    """noteの本文に差し込まれた「生活の一行」＝佇まい／労いの一滴を拾う。

    処方の説明ではなく、Cocoの暮らしとして挿し込まれる行。形は決まっていて、
    「〜するのも、〜」「〜くらいでちょうどいい」の**提案形**を取る。
    この枠は E373 の要素だけで書く決まりなので、要素を含まない行は素材外の創作を疑う。

    **構文で絞る理由**：最初は「1文だけの短い段落」で拾ったが、8本で47件当たった。
    定番プロミスも背中押しも冒頭の一行も全部かかり、rules/check.md
    「ツールに合わせて本文を書き換えたら、それは欠陥の報告」が警告している
    過検出そのものになる。**枠に固有の構文だけを見る。**"""
    out = []
    for para in md.split('\n\n'):
        s = para.strip()
        if not s or s.startswith(('#', '>', '-', '*', '|', '[', '**―')): continue
        if len(s) > 60 or s.count('。') > 1: continue
        if INSERT_RE.search(s): out.append(s)
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
    inserted = []
    for f in files:
        label = os.path.basename(f)
        try:
            d = json.load(open(f, encoding='utf-8'))
        except (OSError, ValueError) as e:
            print(f'  読めない: {f} ({e})')
            return 1
        for pid, body in items(d, label):
            for e in els:
                if e in body:
                    hits[e].append(f'{label}:{pid}')
        if 'posts' not in d:
            for s in inserted_lines(d.get('content_markdown', '')):
                inserted.append((label, s, [e for e in els if e in s]))

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

    if inserted:
        bare = [x for x in inserted if not x[2]]
        print(f'\n■ noteに差し込まれた一行（{len(inserted)}件・E373の要素だけで書く枠）')
        for label, s, es in inserted:
            print(f'  {"　" if es else "!"} {label.replace("note_","").replace(".json","")}  {s}'
                  + (f'  ← {"／".join(es)}' if es else '  ← E373の要素なし・要目視'))
        if bare:
            print(f'  ※ ! の{len(bare)}件は、E373 に無い生活描写の疑い。'
                  '素材にあるかを台帳で確かめ、無ければ要素に差し替える')

    unused = [e for e in els if e not in hits]
    print(f'\n■ この週で未使用の要素（差し替えに使える）\n  {" ／ ".join(unused) if unused else "（なし）"}')

    print('\n' + '=' * 60)
    print('【判断チェック】機械では判定できない。必ず目視で埋めること')
    print('=' * 60)
    print('① 素材の線引き — わたしの習慣の形（「わたしは〜してる」「〜する。」）で書いた一行は、')
    print('   E373 の要素だけで書けているか。ゼロ主語の軽い一行は E373 に限らない')
    print('   （2026-08-29 Coco決定・恒久ルール）')
    # ⚠️ 旧文「episode_id が E373 になっているか（佇まい枠の素材は E373）」は削除した
    # （2026-09-03）。E454 を佇まい枠の素材として受領した時点で、E373 だけという前提が
    # 崩れている。IDを直書きせず、台帳の band から拾う（e373.tatazumai_ids）
    print(f'② 佇まい枠の episode_id が {"・".join(sorted(e373.tatazumai_ids()))} のどれかか')
    print('   （佇まい枠の素材は、台帳で band に「佇まい枠」を持つエピソード。IDを覚えない）')
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
