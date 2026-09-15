#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canon_check.py ── 正典がひとつになっているかを見る
=====================================================
CLAUDE.md「正典はひとつ。復唱しない」の機械側。

**なぜ要るか**（2026-09-02 実測）
8/31 に CLAUDE.md の X診断ルールを直したとき、同じ主題を復唱していた
**4箇所が旧版のまま残った**（rules/posts.md の「絶対禁止」・rules/check.md の
一覧・runbook 2本）。しかも旧版は「いかなる場合も変更しない」で、
**Coco本人の名指しの指示を弾く側の文**だった。同じ事故は 8/31 にも起きている。

2回の点検で見つけた **13件のうち11件**が「その回の変更が置き去りにしたもの」。
つまり壊れるのは直した場所ではなく、**直した場所を復唱していた場所**。
人が毎回 grep で追うのは続かないので、ここに置く。

**このツールは候補を出すだけ。判定は目で決める。**
過検出は欠陥なので（ツールに合わせて本文を書き換えることになる）、
拾いすぎるより取りこぼすほうを選んでいる。

使い方:
    python3 tools/canon_check.py            # 全部
    python3 tools/canon_check.py --ghost    # ①だけ（否定した旧指示の生き残り）
    python3 tools/canon_check.py --num      # ②だけ（数値の二重持ち）
    python3 tools/canon_check.py --echo     # ③だけ（近い文の復唱）
    python3 tools/canon_check.py --samefile # ④だけ（同じファイル内の数値の重複）
    python3 tools/canon_check.py --pointer  # ⑤だけ（ポインタ行が数値を連れている）
    python3 tools/canon_check.py --leak     # ⑥だけ（CLAUDE.md の数値の流出）
    python3 tools/canon_check.py --selfecho # ⑦だけ（同じファイル内の復唱）
"""
import os
import re
import sys
import glob
import collections

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def targets():
    """検査対象。reference/decisions.md と handover は履歴なので外す
    ——旧文をそのまま引用して残すのが仕事のファイルで、ここを叩くと
    「履歴を消せ」という指摘になり、意味が逆になる"""
    fs = [os.path.join(REPO, 'CLAUDE.md')]
    fs += sorted(glob.glob(os.path.join(REPO, 'rules', '*.md')))
    fs += sorted(glob.glob(os.path.join(REPO, 'reference', '*.md')))
    fs += sorted(glob.glob(os.path.join(REPO, 'tools', '*.py')))
    # 履歴は外す（正典は CLAUDE.md「正典はひとつ」の例外①）。
    # report_ は 2026-09-14 に追加——新しい報告書1本で候補が 38→45 に増えた。
    # 報告書は handover と同じ履歴で、旧文をそのまま残すのが仕事
    # og_headlines_ は週ごとのデータ。週が増えるたびに前週と当たり、1週で候補が7件増える
    # （2026-09-14 実測：9/15週ぶんが入って 38→45）。似ているのが正常なので外す
    skip = ('decisions.md', 'handover_', 'handoff_', 'report_', 'og_headlines_',
            'canon_check.py')
    return [f for f in fs if not any(s in os.path.basename(f) for s in skip)]


def rel(p):
    return os.path.relpath(p, REPO)


def load():
    out = {}
    for f in targets():
        try:
            out[f] = open(f, encoding='utf-8').read().split('\n')
        except OSError:
            pass
    return out


# ─────────────────────────────────────────────
# ① 否定した旧指示が、どこかで生きて残っていないか
# ─────────────────────────────────────────────
# 「旧記述「…」は削除した」と書いた本人の行はもちろん残る。見たいのは
# **その旧文が、注記のない裸の行としてまだ立っているか**
GHOST = re.compile(
    r'旧(?:記述|指示|表記|ルール|版|文|案|計算)?[「『]([^「」『』\n]{6,80})[」』]'
    r'[^\n]{0,60}?(?:削除|廃止|置き換|撤回|不採用|誤り|やめ|外し|でなく|ではなく)'
)
# 注記側の行に必ず出る語。これを持つ行は「引用」なので生き残りではない。
# 「→」は旧→新の対応表（`rules/type.md` の差し替え表）で、置き換えの記録そのもの
# 鉤括弧の中身。旧文がこの中にあるなら、それは引用であって生き残りではない
QUOTE_SPAN = re.compile(r'[「『]([^「」『』\n]*)[」』]')
QUOTED = ('旧記述', '旧指示', '旧表記', '旧ルール', '旧版', '旧文', '旧案', '旧計算',
          '削除', '廃止', '置き換', '撤回', '不採用', '誤り', '矛盾', '見直す',
          '→', '統合した')


def ghost_check(docs):
    hits = []
    for f, lines in docs.items():
        for i, l in enumerate(lines, 1):
            for m in GHOST.finditer(l):
                old = m.group(1).strip()
                # 短すぎる・記号だけの引用は照合しても意味が出ない
                if len(old) < 6:
                    continue
                for g, glines in docs.items():
                    for j, gl in enumerate(glines, 1):
                        if g == f and j == i:
                            continue
                        if old not in gl:
                            continue
                        if any(q in gl for q in QUOTED):
                            continue   # そこも引用として書いている
                        if any(old in q for q in QUOTE_SPAN.findall(gl)):
                            continue   # 鉤括弧の中にある＝引用。裸で立っていない
                        hits.append((old, rel(f), i, rel(g), j, gl.strip()))
    return hits


STRIP = re.compile(r'[*`｜|、。「」『』（）()\[\]\s・:：—\-#>＝=／/]')
# ファイル名・パスは「復唱」ではない。同じファイルを指す行が2箇所にあるのは当たり前で、
# ③⑦はそこで一致して大量に当たっていた（2026-09-15 実測：③の18件中15件が
# `reference/weekly_metrics.json` などのパス一致だけで、中身は全部別の話だった）。
# **比べる前にパスを落とす。** 残りが短すぎる行は、そもそも比べない
PATH = re.compile(r'[\w/]+\.(?:json|md|py|html|js|css|png|txt)')


def norm(s):
    return STRIP.sub('', PATH.sub('', s))


# ─────────────────────────────────────────────
# ② 同じ数値が、2つ以上のファイルで規定として立っていないか
# ─────────────────────────────────────────────
# **2桁以上に限る。** 1桁（1本・2回・1日…）は主題が違っても必ずぶつかるので、
# 入れると候補が数十件になる。過検出は欠陥——ツールに合わせて本文を書き換える
# ことになるので、**取りこぼすほうを選ぶ**（2026-09-02 実測：1桁を入れると
# 「1本」だけで18行出て、うち規定の二重持ちは0件だった）
NUM = re.compile(r'(?:週)?\d[\d,]*\d(?:幅|字|本|円|%|人|問|日|回)')
# ⑥用。1桁も拾う（⑥は3桁以上に自分で絞るので、2桁縛りは要らない）
NUM_ANY = re.compile(r'\d[\d,]*(?:幅|字|本|円|%|人|問|日|回)')
# 正典を指している行・履歴を語っている行は数えない
POINTER = ('正典', '複製を置かない', 'ここに数字を書かない', '実例', '実測',
           '旧', '参考', '根拠', '背景', '——', 'だった')
# 規定として立っている合図
NORMATIVE = ('上限', '以内', 'まで', '固定', '超えない', '下限', '目安', 'にする', 'で作る')


# 規定として立っている行が、この数を超えて出る数値は「よく出る数」。
# 主題が違っても必ずぶつかるので見ない
RARE = 6


def num_check(docs):
    where = collections.defaultdict(list)
    for f, lines in docs.items():
        for i, l in enumerate(lines, 1):
            if l.strip().startswith(('#', '```')):
                continue
            if any(p in l for p in POINTER):
                continue
            if not any(n in l for n in NORMATIVE):
                continue
            for tok in set(NUM.findall(l)):
                where[tok].append((rel(f), i, l.strip()))
    out = []
    for tok, v in sorted(where.items()):
        if len({x[0] for x in v}) < 2:
            continue
        # **珍しい数値だけを見る。** よく出る数（14本・週2本…）は主題が違っても
        # 必ずぶつかる。逆に 249幅・350字 のような数は、出てくる場所が少なく、
        # 出たら同じ主題であることがほとんど。
        # ⚠️ 最初は「周りの言葉が重なっている組だけ残す」で書いたが、**今日の実物
        # （249幅が shindan.md と check.md にあった状態）を再現しても0件だった**。
        # 検出力ゼロのチェックは、安心だけ配ってこのルールを邪魔する。だから捨てた
        if len(v) <= RARE:
            out.append((tok, v))
    return out


def pointer_num(docs):
    """⑤ ポインタだと名乗っている行が、数値を連れていないか。

    ②④は `POINTER` に当たる行を**最初に捨てている**（「正典は◯◯」「ここに複製を
    置かない」と書いてある行は、片付いている印だとみなしていた）。
    そこが 2026-09-15 の実害になった——`rules/note.md` の点検で人が拾った10件のうち、
    **6件がこの形**（正典は `CLAUDE.md` と書いてある行が、括弧の中に価格と会員数を
    連れていた）。②にも④にも1件も出ていない。`rules/posts.md` 96行も同じ形だった。

    **「ここに複製を置かない」と書いた当の行が、複製を持っている。**
    片付いている印が、いちばん見落とされる。

    実測は除く（表示回数・実際に何本あったか）。**あれは履歴なので古くならない**
    ——CLAUDE.md「数と一覧は、正典以外に書き写さない」の例外。
    """
    # 「この行はポインタです」と名乗っている合図
    DECLARE = ('正典', '複製を置かない', 'ここに数字を書かない', 'ここに数を書かない',
               '書き写さない', 'そちらが正典', '複製を置いていない')
    # 履歴（古くならない）と、数そのものが主題の行は除く
    EXEMPT = ('実測', '実例', '旧', '履歴', '時点', '閾値はツールが持つ',
              # **その行自身が正典だと名乗っている**形。数を持っていて正しい
              'ここが', 'この行が', 'この節が', 'この表')
    # 正典の**節の名前**が数を含んでいるだけの引用は数えない。
    # CLAUDE.md「指すときは、数ではなく名前で指す」に従った結果そうなるので、
    # ここで叩くと「名前で指すな」という逆の指摘になる
    QUOTE = re.compile(r'(?:正典は|上の|下の)?\s*(?:`[^`]+`)?\s*「[^」]*」')
    # 履歴の括弧（「（2026-09-13：…）」）。中の数は事故の記録なので古くならない
    RECORD = re.compile(r'（20\d\d-\d\d-\d\d[^）]*）')
    out = []
    for f, lines in docs.items():
        # 機械（tools/*.py）は値を持ってよい。**コメントに正典の場所を書く**のが
        # 正しい形なので、ここで叩くと正しい形を叩くことになる
        if f.endswith('.py'):
            continue
        for i, l in enumerate(lines, 1):
            if l.strip().startswith(('#', '```')):
                continue
            if not any(d in l for d in DECLARE):
                continue
            if any(e in l for e in EXEMPT):
                continue
            toks = sorted(set(NUM.findall(QUOTE.sub('', RECORD.sub('', l)))))
            if toks:
                out.append((rel(f), i, toks, l.strip()))
    return out


def self_echo(docs, thresh=0.70, minlen=30):
    """⑦ 近い文が、**同じファイルの中**で繰り返されていないか。

    ③は同じファイル内の組を捨てている（`if rows[a][0] == rows[b][0]: continue`）。
    ②と④で同じことが起きたのと同じ穴で、**毎回読むファイルの中の復唱**は
    ここでしか見えない。2026-09-15 実測：`rules/note.md` が
    「content_markdown と content_html の両方に入れる」を**5箇所**で言い切っていた。

    **毎回読むファイルだけを見る**（`CLAUDE.md` と `rules/`）。
    `reference/` は履歴と指示文で、同じ話が何度も出るのが正常。

    ③より閾値を上げてある（0.70）。同じファイルの中は語彙がそろうので、
    ③の 0.62 だと節の入れ子で当たり前に当たる。
    """
    out = []
    for f, lines in docs.items():
        if not f.endswith('.md'):
            continue
        if os.sep + 'rules' + os.sep not in f and os.path.basename(f) != 'CLAUDE.md':
            continue
        rows = []
        fence = 0          # ``` の中にいるか。0 なら外、>0 ならその開始行
        for i, l in enumerate(lines, 1):
            s = l.strip()
            if s.startswith('```'):
                fence = 0 if fence else i
                continue
            if s.startswith(('#', '|')):
                continue
            n = norm(s)
            if len(n) < minlen:
                continue
            # 注記は「この行の直前2行」を見る。ただし **``` の中にいるときは
            # ブロックの開始行の直前を見る**——貼り付け用の見本は1行ではなく
            # ブロック単位で置かれるので、注記もブロックの上に付く
            # （2026-09-15：`rules/note.md` の💼組織の見本に注記を足しても、
            #  注記がブロックの4行上にあって届いていなかった）
            top = fence if fence else i
            near = ' '.join(lines[max(0, top - 3):top]) + ' ' + l
            rows.append((i, s, n, any(m in near for m in SETTLED)))
        idx = collections.defaultdict(set)
        for k, (_, _, n, _) in enumerate(rows):
            for a in range(0, len(n) - 11, 4):
                idx[n[a:a + 12]].add(k)
        seen = set()
        for _, ks in idx.items():
            if len(ks) < 2 or len(ks) > 40:
                continue
            ks = sorted(ks)
            for x in range(len(ks)):
                for y in range(x + 1, len(ks)):
                    a, b = ks[x], ks[y]
                    if (a, b) in seen:
                        continue
                    seen.add((a, b))
                    na, nb = rows[a][2], rows[b][2]
                    sa = {na[t:t + 8] for t in range(len(na) - 7)}
                    sb = {nb[t:t + 8] for t in range(len(nb) - 7)}
                    if not sa or not sb:
                        continue
                    r = len(sa & sb) / min(len(sa), len(sb))
                    if r < thresh:
                        continue
                    if rows[a][3] or rows[b][3]:
                        continue    # 隣に注記がある＝承知のうえで置いた見本
                    if all(any(m in rows[k][1] for m in SETTLED) for k in (a, b)):
                        continue    # 両方がポインタか記録
                    out.append((round(r, 2), rel(f), rows[a][0], rows[a][1],
                                rows[b][0], rows[b][1]))
    return sorted(out, reverse=True)


def leak_check(docs):
    """⑥ `CLAUDE.md` が持っている珍しい数値が、他のファイルにも立っていないか。

    ②は両方の行が「規定として立っている合図」（上限・まで・固定…）を持つ組しか
    見ない。**表の行や、理由を述べている行は合図を持たない**ので落ちる。
    2026-09-15 の実害がまさにそれだった——`rules/note.md` の価格表の行
    （`| 価格 | 月額1,500円 |`）と会員数の6箇所は、②にも④にも⑤にも出ていない。

    **数値の一覧をここに持たない。** `CLAUDE.md` の本文から拾うので、
    CLAUDE.md の数字が変われば、この検査が見る数字も一緒に変わる
    （CLAUDE.md「数と一覧は、正典以外に書き写さない」）。

    **珍しい数値だけを見る**（3桁以上）。1本・3回のような数は主題が違っても
    必ずぶつかる——②が1桁を捨てたのと同じ理由。
    """
    cl = [l for f, l in docs.items() if os.path.basename(f) == 'CLAUDE.md']
    if not cl:
        return []
    toks = set()
    for l in cl[0]:
        if l.strip().startswith(('#', '```')):
            continue
        # **記録の行は読まない。** ⚠️ 行は削除・訂正の記録＝履歴で、規定ではない
        # （CLAUDE.md「⚠️ 行は記録」）。ここを読むと、削除した数字を
        # 「CLAUDE.md が持っている値」として数え直して、全ファイルに誤検出が出る
        # （2026-09-15 実測：150〜200字を削除した記録を書いた直後、その数字で
        # rules/posts.md の正典3行が候補に上がった）
        if '⚠️' in l or any(e in l for e in ('実測', '実例', '旧')):
            continue
        for t in NUM_ANY.findall(l):
            if len(re.sub(r'[^\d]', '', t)) >= 3:
                toks.add(t)
    out = []
    for f, lines in docs.items():
        if os.path.basename(f) == 'CLAUDE.md' or f.endswith('.py'):
            continue
        for i, l in enumerate(lines, 1):
            if l.strip().startswith(('#', '```')):
                continue
            if any(e in l for e in ('実測', '実例', '旧', '履歴', '時点')):
                continue
            hit = sorted({t for t in NUM_ANY.findall(l) if t in toks})
            if hit:
                out.append((rel(f), i, hit, l.strip()))
    return out


def num_same_file(docs):
    """④ 同じ数値が、**同じファイルの中**で2回以上、規定として立っていないか。

    ②はファイルをまたいだ一致しか見ていない（`len({x[0] for x in v}) < 2: continue`）。
    そこが 2026-09-15 の実害になった——`rules/posts.md` の点検で人が拾った10件は、
    **1件も②に出ていない**。候補が36件のまま動かなかったのはそのため。
    3ファイルを人が通しで読んで初めて出たので、**このままでは再現できない**。

    見出し行は除く（`#`）。**正典側の見出しが数を名前として持っている形**
    （「同じ構文を週内で3本以上使わない」）は、指す側が数を書き写しても
    避けようがないため。ポインタ行と、数値を持たない行も除く。
    """
    out = []
    for f, lines in docs.items():
        where = collections.defaultdict(list)
        for i, l in enumerate(lines, 1):
            if l.strip().startswith(('#', '```')):
                continue
            if any(p in l for p in POINTER):
                continue
            if not any(n in l for n in NORMATIVE):
                continue
            for tok in set(NUM.findall(l)):
                where[tok].append((i, l.strip()))
        for tok, v in sorted(where.items()):
            if 2 <= len(v) <= RARE:
                out.append((rel(f), tok, v))
    return out


# ─────────────────────────────────────────────
# ③ 近い文が、別のファイルで復唱されていないか
# ─────────────────────────────────────────────
# 「もう片付いている」印。両方の行がこれを持つ組は出さない
#   ポインタ同士 ＝ 同じ正典を指しているだけ／記録同士 ＝ 履歴の一致
SETTLED = ('正典', '複製を置かない', 'ここに数字を書かない', '旧版', '旧記述',
           '旧指示', '旧表記', '旧ルール', '削除した', '廃止',
           # 他のファイルの節を名指ししている行は、それ自体がポインタ
           'CLAUDE.md', 'rules/', 'reference/runbook')


def echo_check(docs, thresh=0.62, minlen=28):
    rows = []
    for f, lines in docs.items():
        # **③は md だけ見る。** コードは同じ行が繰り返されて当たり前で
        # （import・描画の定型）、tools/ を入れたら225件中ほぼ全部が
        # og*.py の描画行だった。ツール側の複製は②と、各ツール冒頭の
        # 「定義は1箇所。ここに複製しない」で見る
        if not f.endswith('.md'):
            continue
        for i, l in enumerate(lines, 1):
            s = l.strip()
            if s.startswith(('#', '|', '```', '//', '#!')):
                continue
            # ファイル名の羅列は「復唱」ではない（読み込むものの一覧が
            # 指示文と検査表の両方に出るのは当たり前）。パスが2つ以上あって
            # 他に中身が無い行は落とす
            if len(re.findall(r'[\w/]+\.(?:json|md|py)', s)) >= 2 and len(norm(s)) < 90:
                continue
            n = norm(s)
            if len(n) < minlen:
                continue
            # 直前・直後の行が注記なら、その行は注記つき（貼り付け用の見本など）。
            # 本文そのものには「正典は◯◯」と書けないので、隣の行で受ける形を認める
            near = ' '.join(lines[max(0, i - 2):i + 1])
            rows.append((rel(f), i, s + ('  〔注記あり〕' if any(m in near for m in SETTLED) else ''), n))
    # 12字シングルの転置索引で候補を絞る（総当たりにしない）
    idx = collections.defaultdict(set)
    for k, (_, _, _, n) in enumerate(rows):
        for a in range(0, len(n) - 11, 4):
            idx[n[a:a + 12]].add(k)
    seen, out = set(), []
    for sh, ks in idx.items():
        if len(ks) < 2 or len(ks) > 40:
            continue
        ks = sorted(ks)
        for x in range(len(ks)):
            for y in range(x + 1, len(ks)):
                a, b = ks[x], ks[y]
                if rows[a][0] == rows[b][0]:
                    continue         # 同じファイル内は別ルール（節の入れ子で正しく再掲する）
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                na, nb = rows[a][3], rows[b][3]
                sa = {na[t:t + 8] for t in range(len(na) - 7)}
                sb = {nb[t:t + 8] for t in range(len(nb) - 7)}
                if not sa or not sb:
                    continue
                r = len(sa & sb) / min(len(sa), len(sb))
                if r < thresh:
                    continue
                # **両方がポインタなら、それは正しい形。** 2箇所が同じ正典を
                # 指しているだけで、直す先は1つしかない。ここを出すと
                # 「直しても消えない候補」が並び、次から誰も見なくなる。
                # 同じく、両方が「旧◯◯は削除した」の記録なら履歴の一致
                ta, tb = rows[a][2], rows[b][2]
                # 片方に注記が付いていれば、それは「承知のうえで置いた見本」。
                # 人が判断を残した印なので、毎回出し直さない
                if '〔注記あり〕' in ta or '〔注記あり〕' in tb:
                    continue
                if all(any(m in t for m in SETTLED) for t in (ta, tb)):
                    continue
                out.append((round(r, 2), rows[a][:3], rows[b][:3]))
    out.sort(reverse=True)
    return out


def main(argv):
    only = {a for a in argv if a.startswith('--')}
    docs = load()
    n = 0

    if not only or '--ghost' in only:
        h = ghost_check(docs)
        print('\n① 否定した旧指示が、まだ裸で残っていないか')
        print('   ——「削除した」と書いた本人の行以外に、その旧文が立っていないか見る')
        if not h:
            print('   なし')
        for old, f, i, g, j, gl in h:
            print(f'   ⚠ 「{old}」')
            print(f'      否定: {f}:{i}')
            print(f'      残存: {g}:{j}  {gl[:90]}')
        n += len(h)

    if not only or '--num' in only:
        d = num_check(docs)
        print('\n② 同じ数値が、2つ以上のファイルで規定として立っていないか')
        print('   ——片方が正典、片方がポインタなら出ない。両方が言い切っている時だけ出る')
        if not d:
            print('   なし')
        for tok, v in d:
            print(f'   ⚠ {tok}')
            for f, i, l in v:
                print(f'      {f}:{i}  {l[:88]}')
        n += len(d)

    if not only or '--echo' in only:
        e = echo_check(docs)
        print('\n③ 近い文が、別のファイルで復唱されていないか')
        print('   ——完全一致は目で見つからない。似ているだけの復唱がいちばん腐る')
        if not e:
            print('   なし')
        for r, (f, i, s), (g, j, t) in e[:30]:
            print(f'   ⚠ 一致度 {r}')
            print(f'      {f}:{i}  {s[:88]}')
            print(f'      {g}:{j}  {t[:88]}')
        if len(e) > 30:
            print(f'   （ほか {len(e) - 30} 組）')
        n += len(e)

    if not only or '--samefile' in only:
        d4 = num_same_file(docs)
        print('\n④ 同じ数値が、同じファイルの中で2回以上、規定として立っていないか')
        print('   ——②はファイルをまたいだ一致しか見ない。2026-09-15 に人が拾った10件は')
        print('     1件も②に出なかった。見出し行とポインタ行は除いてある')
        if not d4:
            print('   なし')
        for f, tok, v in d4[:30]:
            print(f'   ⚠ {f}  {tok}')
            for i, l in v:
                print(f'      :{i}  {l[:84]}')
        if len(d4) > 30:
            print(f'   （ほか {len(d4) - 30} 組）')
        n += len(d4)

    if not only or '--pointer' in only:
        d5 = pointer_num(docs)
        print('\n⑤ ポインタだと名乗っている行が、数値を連れていないか')
        print('   ——②④はこの形の行を最初に捨てている。2026-09-15 に人が拾った10件のうち')
        print('     6件がここだった。「複製を置かない」と書いた当の行が複製を持つ形')
        if not d5:
            print('   なし')
        for f, i, toks, l in d5[:30]:
            print(f'   ⚠ {f}:{i}  {"・".join(toks)}')
            print(f'      {l[:96]}')
        if len(d5) > 30:
            print(f'   （ほか {len(d5) - 30} 行）')
        n += len(d5)

    if not only or '--leak' in only:
        d6 = leak_check(docs)
        print('\n⑥ `CLAUDE.md` が持つ珍しい数値（3桁以上）が、他のファイルにも立っていないか')
        print('   ——②は「上限・まで・固定」の合図を持つ行しか見ない。表の行と理由の行は')
        print('     合図を持たないので落ちる。2026-09-15 の価格・会員数6件がこれだった')
        if not d6:
            print('   なし')
        for f, i, hit, l in d6[:40]:
            print(f'   ⚠ {f}:{i}  {"・".join(hit)}')
            print(f'      {l[:96]}')
        if len(d6) > 40:
            print(f'   （ほか {len(d6) - 40} 行）')
        n += len(d6)

    if not only or '--selfecho' in only:
        d7 = self_echo(docs)
        print('\n⑦ 近い文が、同じファイルの中で繰り返されていないか（毎回読むファイルだけ）')
        print('   ——③は同じファイル内の組を捨てている。②④と同じ穴で、')
        print('     毎回読むファイルの中の復唱はここでしか見えない')
        if not d7:
            print('   なし')
        for r, f, i, a, j, b in d7[:30]:
            print(f'   ⚠ 一致度 {r}  {f}:{i} / :{j}')
            print(f'      {a[:92]}')
            print(f'      {b[:92]}')
        if len(d7) > 30:
            print(f'   （ほか {len(d7) - 30} 組）')
        n += len(d7)

    print(f'\n■ 候補: {n}件')
    print('  **これは候補であって判定ではない。** 片方が正典・片方がポインタなら正しい形。')
    print('  同じ主題を2箇所が言い切っていたら、正典を1つ決めて残りをポインタにする。')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
