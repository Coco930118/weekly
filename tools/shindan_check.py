#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""診断7本の恒久ルール全チェック（X診断・Threads診断 共通の入口）

使い方:  python3 tools/shindan_check.py posts/shindan_x_YYYY-MM-DD.json
        python3 tools/shindan_check.py posts/shindan_th_YYYY-MM-DD.json
        python3 tools/shindan_check.py posts/shindan_*_2026-09-01.json

【重要】機械で検出できるルールだけを見る。判断が要るもの（焦点の一貫性／舐められず
好かれる／既視感ゼロ／比喩ゼロ／設問の型の妥当性）は末尾の「判断チェック」に出す。
機械チェックだけで「全項目クリア」と報告しない。

ルール本体は rules/shindan.md。項目を足したくなったら、その場でスクリプトを
書かずにこのファイルを更新する。
"""
import json, re, sys, glob, os, collections, unicodedata
import e373

BANNED = ['設計', '構造', '体制', '仕組み', '熱量', '消耗', '削れる', '明け渡す',
          '渡す', '渡し', '恋人', '寄り添', 'んです', 'と言えるでしょう', 'いかがでしょうか',
          '大切なのは', '台所']   # 「大切なのは」＝CLAUDE.md 文体のAI定型。note_check にしか無かった（2026-08-29 補完）
STYLE_ONLY = ['んです', 'と言えるでしょう', 'いかがでしょうか', '寄り添']
# 設問の主語（rules/shindan.md「文体」・2026-08-25 Coco決定／9/1週から適用）
# frame だけを見る：解説の地の文で語そのものを説明する場合があり、そこは射程外
SUBJECT_NG = ['あなた', 'みんな']
SUBJECT_FROM = '2026-09-01'

X_CTA = 'いちばん近いの、一文字だけコメントで教えて。'
X_FOUR = '四つとも、間違いではない。'
X_BRIDGE = 'さっきの4択が1問目。残り7問で出るのは、その場面ではなく、いつもの判断のほう。'
X_TAIL = '▼ 8問 / 約1分'
TH_BRIDGE = 'さっきの4択が1問目。残り7問で出るのは、その場面ではなく、いつもの癖のほう。'
TH_STAR = '感情はある。依存はしない。'
TH_TAIL = '▼ 8問 / 約1分'          # 正文（2026-08-25 Coco決定・8/25週から）。
TH_TAIL_OLD = '▼ 8問 / 約1分で、いまどこに立っているか'   # 旧文。橋渡しの一行と約束が重なるため廃止
# 混入文字：キリル・ハングルは日本語の投稿に出ない。手打ち経路で紛れると目視で気づけない
MOJI = re.compile(r'[Ѐ-ӿ가-힣]')
MEMBERSHIP = 'note.com/coconocanvas/membership'

# 設問の型（実測の到達率：見立て170/166・順番144・自己分類114・行動96）
QTYPE = [('見立て', ['何を疑う', 'どう見る', 'どこを見る', '何を見る', 'どう読む', '何が起きて']),
         ('順番',   ['先に', '何から', 'どこから', '最初に', '順番']),
         ('自己分類', ['一番近い', 'いちばん近い', '一番気にする', 'どれが近い']),
         ('行動',   ['どう動く', 'どうする', 'どう返す', 'どう伝える', '何と言う'])]
# 佇まいの一行の候補。素材側（E373）は台帳から読む——手で持つと素材を足しても検出が
# 追随せず、逆に台帳に無い語（湯船など）を正解として検出し続ける（2026-08-29 Wチェック）。
# 言い回し側は、ゼロ主語の軽い一行を拾うための構文ヒント。
# ①ウィット一滴の素材は、わたしの習慣の形で書く場合だけ E373 に限る／ゼロ主語は限らない
# （2026-08-29 Coco決定・恒久ルール）。ここは候補の検出であって、素材の可否判定ではない
WIT_SYNTAX = ['お茶', 'コーヒー', 'ごはん', '一杯', '甘いもの', '飲んで', 'それだけ。']
WIT_HINTS = e373.elements() + WIT_SYNTAX

issues = []
CURRENT = ['']   # いま検査中のファイル名。指摘の出力は最後に一括なので、
                 # これが無いとX診断とThreads診断のどちらの指摘か区別できない
                 # （両ファイルとも日付をIDに使うため。2026-08-29 Wチェック指摘）
def ng(pid, *m):
    head = f'{CURRENT[0]} {pid}' if CURRENT[0] else str(pid)
    issues.append(f'{head}: ' + ' '.join(str(x) for x in m))

def width(s):
    """全角2・半角1・改行1で数える（Xの280字判定）"""
    return sum(1 if unicodedata.east_asian_width(c) in 'HNa' or c == '\n' else 2 for c in s)

def banned_in(text):
    naked = re.sub(r'「[^」]*」', '', text)   # 読者の声の引用内は文体ルールの対象外
    return [w for w in BANNED if (w in naked if w in STYLE_ONLY else w in text)]


def subject_in(frame, date):
    """設問の主語。frame 限定・引用の「」内は対象外・9/1週より前には遡及しない"""
    if date < SUBJECT_FROM: return []
    naked = re.sub(r'「[^」]*」', '', frame)
    return [w for w in SUBJECT_NG if w in naked]


def check_x(posts, label):
    print(f'--- X診断 {len(posts)}本 ---')
    wit, qt = [], []
    for p in posts:
        pid = p['date']
        fr, cm = p.get('frame', ''), p.get('comment', '')

        # 1 frame：280字上限（超えるとタイムラインで折り畳まれ、設問とCTAが初見で見えない）
        w = width(fr)
        if w > 280: ng(pid, f'frameが{w}字（上限280）。フックを引き算して収める')

        # 2 固定要素
        if X_CTA not in fr: ng(pid, f'固定CTA「{X_CTA}」がない')
        if X_FOUR not in fr: ng(pid, f'「{X_FOUR}」がない')
        if not re.search(r'#温度の4択\s+\d{3}', fr): ng(pid, 'ハッシュタグ `#温度の4択 NNN` がない')
        for a in 'ABCD':
            if f'{a}．' not in fr and f'{a}｜' not in fr: ng(pid, f'選択肢{a}がない')

        # 3 comment は1通（旧 comment_1 / comment_2 の2通構成は廃止）
        if 'comment_1' in p or 'comment_2' in p: ng(pid, '旧形式（comment_1 / comment_2）が残っている')
        if not cm: ng(pid, 'comment がない')

        # 4 接続の一行（固定要素。7本バラバラに書き換えない）
        if X_BRIDGE not in cm: ng(pid, '接続の一行が固定文と違う（既視感チェックの対象外・7本同一）')
        if X_TAIL not in cm: ng(pid, f'「{X_TAIL}」がない')

        # 5 診断URLがコメントの最終行
        url = p.get('shindan_url', '')
        if not re.match(r'https://shindan-flax\.vercel\.app/soshiki/\d\d-\d\d$', url):
            ng(pid, f'診断URLの形式が違う: {url}')
        last = [l for l in cm.strip().split('\n') if l.strip()][-1]
        if url not in last: ng(pid, 'コメントの最終行が診断URLになっていない')

        # 6 廃止したもの
        if MEMBERSHIP in cm: ng(pid, 'メンバーシップCTAがコメントに残っている（会員導線は診断サイト側）')
        if 'これまでの診断' in cm: ng(pid, 'バックカタログ行が残っている（新形式で廃止）')
        if p.get('image_prompt'): ng(pid, 'image_prompt を持っている（診断は画像プロンプト廃止）')

        # 7 禁止語・混入文字
        h = banned_in(fr + cm)
        if h: ng(pid, '禁止語', '／'.join(h))
        m = MOJI.findall(fr + cm)
        if m: ng(pid, '混入文字（キリル・ハングル）', '／'.join(sorted(set(m))))
        sb = subject_in(fr, pid)
        if sb: ng(pid, '設問に主語', '／'.join(sb), '（frame限定・9/1週から）')

        # 8 参考カウント
        if any(k in cm for k in WIT_HINTS): wit.append(pid)
        t = next((n for n, ks in QTYPE if any(k in fr for k in ks)), '不明')
        qt.append((pid, t))

    print(f'  ウィット一滴 候補: {len(wit)}本 {wit}（試験中・週2〜3本・**目視で確定すること**）')
    c = collections.Counter(t for _, t in qt)
    print(f'  設問の型: {dict(c)}')
    if c.get('行動', 0) > 2: ng(label, f'素の行動型が{c["行動"]}本（上限2本・到達率96%で最下位）')
    for pid, t in qt:
        if t == '不明': print(f'    ! {pid} 設問の型を判定できず（目視）')


def check_th(posts, label):
    print(f'--- Threads診断 {len(posts)}本 ---')
    wit, opens = [], []
    for p in posts:
        pid = p['date']
        fr, r1 = p.get('frame', ''), p.get('reply_1', '')

        # 1 本文にリンクを置かない（8/18週の実測：本文にURLを置いた日はリーチが約8分の1）
        if 'http' in fr: ng(pid, '本文（frame）にURLがある。リンクはコメント末尾の1本だけ')

        # 2 持ち帰れる一行
        if not p.get('takeaway_line'): ng(pid, 'takeaway_line がない')
        elif p['takeaway_line'] not in fr: ng(pid, 'takeaway_line が本文に入っていない')
        elif p['takeaway_line'] in r1: ng(pid, '持ち帰れる一行がコメントと同じ文（本文＝言い切り／コメント＝理由で角度を変える）')

        # 3 返信欄の並び
        b = r1.count('・')
        if b < 4: ng(pid, f'4行の箇条書きが{b}行（A〜Dを全部肯定で拾う）')
        if TH_STAR not in r1: ng(pid, f'北極星「{TH_STAR}」がない')
        if TH_BRIDGE not in r1: ng(pid, '橋渡しの一行が固定文と違う（既視感チェックの対象外・7本同一）')
        if TH_TAIL not in r1: ng(pid, f'「{TH_TAIL}」がない')
        if TH_TAIL_OLD in r1: ng(pid, f'診断リンクが旧文（「{TH_TAIL_OLD}」は2026-08-25に廃止）')
        if MEMBERSHIP in r1: ng(pid, '会員導線が返信欄にある（診断リンクの先にあるため置かない）')

        # 4 診断URL
        url = p.get('shindan_url', '')
        if not re.match(r'https://shindan-flax\.vercel\.app/kankei/\d\d-\d\d$', url):
            ng(pid, f'診断URLの形式が違う: {url}')
        elif url not in r1: ng(pid, '返信欄に診断URLがない')

        # 5 廃止したもの
        if '──────────────' in r1: ng(pid, '旧形式の区切り線が残っている（4行の箇条書きに圧縮する）')
        if p.get('image_prompt'): ng(pid, 'image_prompt を持っている（診断は画像プロンプト廃止）')

        # 6 禁止語・混入文字
        h = banned_in(fr + r1)
        if h: ng(pid, '禁止語', '／'.join(h))
        m = MOJI.findall(fr + r1)
        if m: ng(pid, '混入文字（キリル・ハングル）', '／'.join(sorted(set(m))))
        sb = subject_in(fr, pid)
        if sb: ng(pid, '設問に主語', '／'.join(sb), '（frame限定・9/1週から）')

        # 7 既視感：フックの書き出しと受け口
        opens.append((pid, fr.strip()[:12], r1.strip()[:14]))
        if any(k in r1 for k in WIT_HINTS): wit.append(pid)

    print(f'  ウィット一滴 候補: {len(wit)}本 {wit}（試験中・週2〜3本・**目視で確定すること**）')
    for key, name in ((1, 'フックの書き出し'), (2, '返信の受け口')):
        c = collections.Counter(o[key] for o in opens)
        d = [k for k, v in c.items() if v > 1]
        if d: ng(label, f'{name}が重複: {d}（7本すべて言い回しを変える）')


def main(paths):
    for path in paths:
        d = json.load(open(path, encoding='utf-8'))
        posts = d['posts']
        name = os.path.basename(path)
        CURRENT[0] = name
        print(f'=== 機械チェック: {name} ===')
        (check_x if '_x_' in name else check_th)(posts, name)
        print()

    if issues:
        print(f'■ 機械チェック: 要修正 {len(issues)}件')
        for i in issues: print('  -', i)
    else:
        print('■ 機械チェック: 要修正 0件')

    print('\n' + '=' * 60)
    print('【判断チェック】機械では判定できない。必ず目視で埋めること')
    print('=' * 60)
    print('① 焦点の一貫性 — frame（フック＋設問）と4択が同じ1つの軸を指しているか。')
    print('   解説・締めもその軸から外れていないか')
    print('② 舐められず好かれる — 効く選択肢が「芯がある」と「角が立たない」を両方満たすか。')
    print('   誤答は感情的な批判ではなく構造的な理由で説明できているか')
    print('③ 既視感ゼロ — 7本を横断して、似た表現・似た構文がないか。前週とも突き合わせる')
    print('   （北極星と橋渡しの一行は固定要素。対象外）')
    print('④ 比喩ゼロ・言い切り — 診断は比喩を使わない。核心はそのままの言葉で言い切る')
    print('⑤ 答えの位置 — 効く選択肢の位置（A/B/C/D）が前回までと変わっているか。')
    print('   正解を1つに絞らない回も混ざっているか')
    return 1 if issues else 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    fs = [f for a in sys.argv[1:] for f in sorted(glob.glob(a))]
    sys.exit(main(fs))
