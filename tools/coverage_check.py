#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coverage_check.py ── 禁止した語が、機械に載っているか
=====================================================
`CLAUDE.md`「禁止ルールは、足す前に『機械か、生成か』を決める」①の機械側。

**なぜ要るか**（2026-09-14〜16 実測）
「残る／残す」は Coco が 2026-09-14 に禁止したのに、**どのファイルにも
ツールにも入らないまま3週間置かれた**。その間に**3セッションが3通りに解釈した**
——X本文は全部外し、note は「`rules/note.md` に無いので違反ではない」として残し、
タグラインは判断待ちに上がった。**条文に書いただけの禁止は、守られない。**

同じ形が他にもあった。プロフィールは 2026-09-02 まで**どのツールの対象でもなく**、
引き算の動詞（やめる／畳む…）の上限は 2026-08-27 からあったのに機械が見ておらず、
**9/15週は上限3に対して11本**——一度も止まっていなかった。

**だから、条文の「◯◯は使わない」を集めて、その語が tools/ のどこにも
出てこないものを出す。** 出たものは3つのどれか——
  ① ツールに載せ忘れた（→ 載せる）
  ② 機械では見えない（→ `CLAUDE.md`②の「こう書け」に翻訳する）
  ③ どちらも無理（→ `CLAUDE.md`③。そのルールは足さない）

**このツールは候補を出すだけ。判定は目で決める。**

使い方:
    python3 tools/coverage_check.py
"""
import os
import re
import sys
import glob

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 「◯◯」の直後に禁止の述語が続く形だけを拾う。
# **鉤括弧を無条件に拾うと271件出て、うち実物は1割以下だった**（2026-09-16 実測）。
# 節の名前・言い換えの例・説明の引用が全部かかるため、述語との隣接を条件にする
BAN = re.compile(
    r'[「『]([^「」『』]{2,16})[」』](?:\*\*)?(?:[はをも、／/・）)]|」|\s)*(?:\*\*)?'
    r'(?:は|を|も)?\s*(?:使わない|使用禁止|禁止|置かない|入れない|書かない|並べない|作らない|排除)'
)
# 語そのものではなく形の指定を指している引用は数えない
SKIP = ('〜する', 'こう書け')


def targets():
    fs = [os.path.join(REPO, 'CLAUDE.md')]
    fs += sorted(glob.glob(os.path.join(REPO, 'rules', '*.md')))
    return fs


LITERALS = None


def literals(blob):
    """ツールが持っている文字列リテラル。禁止語はここに入る"""
    return {m for m in re.findall(r"'([^'\n]{2,30})'", blob)
            if not re.search(r'[a-zA-Z0-9_./%{}]', m)}


def expand(blob):
    """`残[るらりれっさしすせそ]` のような形を、具体語に開く。

    ⚠️ 最初は「正規表現をそのまま集めて `re.search` で当てる」で書いたが、
    **検出力ゼロだった**（2026-09-16 実測）。`[一-龥]{2,}` のような
    **何にでも当たる汎用の式**が混ざり、全部「載っている」になっていた。
    **開いて具体語にすれば、当たるのはその語だけになる。**
    """
    out = set()
    for m in re.findall(r"'([^'\n]{2,60})'", blob):
        for head, cls in re.findall(r'([^\x00-\x7f])\[([^\]]{2,20})\]', m):
            if re.search(r'[a-zA-Z0-9\-^]', cls):
                continue
            for c in cls:
                out.add(head + c)
    return out


def tools_text():
    return ''.join(open(f, encoding='utf-8').read()
                   for f in sorted(glob.glob(os.path.join(REPO, 'tools', '*.py')))
                   if os.path.basename(f) != 'coverage_check.py')


def covered(term):
    """ツールの **文字列リテラル** だけを見る。

    ⚠️ 最初は「tools/*.py の本文に出てくるか」で書いたが、**検出力ゼロだった**
    （2026-09-16 実測：「残る」をツールから抜いた 2026-09-14 の状態を再現しても
    0件。理由は、**コメントに「『配合』は…」と書いてあるとそこに当たる**——
    つまり「ツールがコメントでその語に触れている」だけで「載っている」と
    判定していた）。**検出力ゼロの検査は、安心だけ配る。**

    見るのはリテラルだけ。ツールが実際に照合に使っている語はそこにしかない。
    """
    t = term.replace('**', '').replace('〜', '').strip()
    if len(t) < 2:
        return True
    # 条文は「残る／残す」のように並べて書く。**全部が載っていたら載っている**
    parts = [x for x in re.split(r'[／/・、]', t) if len(x) >= 2]
    if len(parts) > 1:
        return all(covered(x) for x in parts)
    for lit in LITERALS:
        # **ほぼ一致だけを「載っている」とみなす。**
        # 「lit がどこかに含まれていれば載っている」にすると、
        # 'あなた'（診断の主語チェック）が「あなたは、どの子？」（OGの見出し）を
        # 消してしまう——まったく別のルールなのに
        if lit == t or t in lit:
            return True
        if any(t[:len(t) - k] == lit for k in (1, 2) if len(t) - k >= 2):
            return True
    return False


def main():
    global LITERALS
    blob = tools_text()
    LITERALS = literals(blob)
    LITERALS |= expand(blob)
    out, seen = [], set()
    for f in targets():
        rel = os.path.relpath(f, REPO)
        for i, l in enumerate(open(f, encoding='utf-8').read().split('\n'), 1):
            if '⚠️' in l or l.strip().startswith(('#', '```')):
                continue          # ⚠️ は記録（CLAUDE.md「⚠️ 行は記録」）
            for q in BAN.findall(l):
                t = q.replace('**', '').replace('〜', '').strip()
                if re.search(r'[a-zA-Z0-9_./]', t) or t in SKIP or len(t) < 2:
                    continue
                if covered(t) or t in seen:
                    continue
                seen.add(t)
                out.append((rel, i, t, l.strip()))

    print('\n■ 条文で禁止しているのに、どのツールも見ていない語')
    print('  ——「機械か、生成か」①。条文に書いただけの禁止は守られない')
    if not out:
        print('   なし')
    for rel, i, t, l in out:
        print(f'   ⚠ 「{t}」  {rel}:{i}')
        print(f'      {l[:100]}')
    print(f'\n■ 候補: {len(out)}件')
    print('  **候補であって判定ではない。** 3つのどれかを選ぶ——')
    print('   ① ツールに載せる ／ ② 「こう書け」に翻訳する ／ ③ そのルールを足さない')
    return 0


if __name__ == '__main__':
    sys.exit(main())
