#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""noteの恒久ルール全チェック

使い方:  python3 tools/note_check.py notes/note_2026-08-26_subtract.json
        python3 tools/note_check.py notes/note_2026-08-2*.json
        python3 tools/note_check.py --week 2026-08-25_2026-08-31
        python3 tools/note_check.py --all          # index掲載の全note

【重要】機械で検出できるルールだけを見る。判断が要るもの（ブランド整合性／到達力／
読了と納得／在り方の一言が記事ごとに違うか）は末尾の「判断チェック」に出す。
機械チェックだけで「全項目クリア」と報告しない。

ルール本体は rules/note.md。項目を足したくなったら、その場でスクリプトを
書かずにこのファイルを更新する。
"""
import json, re, sys, glob, os, collections

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 禁止語の定義は full_check.py が正典。**ここに複製を置かない**（2026-09-02 統一）。
# note だけ「渡す／渡し」を参考カウントに回すので、WATASU_RE は下で別に持つ
from full_check import BANNED
# rules/posts.md が禁じているのは**比喩的な用法**だけで、置き換え先は「言う／頼む／話す／送る／伝える」。
# ところが note では「仕事を人に渡す＝委譲」という**実際の行為**として使われ、130本中11本・
# 延べ128箇所に出る（記事タイトルにも入っている：「答えを渡すのをやめた日」「教えると、伝わらない。
# 渡すと、その人のものになる」）。これを要修正で出し続けると、通すために本文を曲げるか無視するかの
# 二択になり、rules/check.md「ツールに合わせて本文を書き換えたら、それは欠陥の報告」が
# 警告している状態そのものを作る。**候補として出し、比喩かどうかは目視で決める。**
# 短文（35投稿・診断）は比喩の可能性が高く過検出もほぼ無いので、そちらは要修正のまま。
# 活用形まで数える（2026-08-31 Coco決定・恒久ルール）。note では要修正ではなく参考カウントのまま
WATASU_RE = r'渡[すしせさそっ]'
PROMISE = 'メンバーシップは、毎週深堀りが増えて、過去の整え方もぜんぶ読めます。'
PAYWALL = '―――― ここから先は、メンバーシップの中で読めます ――――'
MEMBERSHIP_URL = 'https://note.com/coconocanvas/membership'
PLAN = {'X': '💼', 'Threads': '💗'}
NUMS = ['20年', '5万人', '40名', '月商']
# 画像プロンプト（rules/image.md ／ 正典は reference/image_prompt_rules.json）
CANVA_NG = ['young woman', 'brand age 40s', 'drawn to look', 'youthful',
            'complexion', 'chest', 'bust-up', ' bust']
MONTH_MOTIF = {
    1: ['camellia', 'nandina', 'narcissus', 'first snow', 'bare tree', 'lantern'],
    2: ['plum', 'winter camellia', 'narcissus', 'lingering snow', 'adonis'],
    3: ['plum', 'rape blossom', 'daphne', 'horsetail', 'cherry'],
    4: ['cherry', 'wisteria', 'azalea', 'haze', 'swallow'],
    5: ['wisteria', 'azalea', 'fresh green', 'iris', 'rose', 'young leaves'],
    6: ['hydrangea', 'rain', 'young green', 'green plum', 'iris', 'firefly'],
    7: ['morning glory', 'lotus', 'firefly', 'wind chime', 'lantern', 'evening shower'],
    8: ['crape myrtle', 'sunflower', 'moonflower', 'cicada', 'summer moon', 'dragonfly'],
    9: ['pampas', 'harvest moon', 'cosmos', 'bush clover', 'dragonfly'],
    10: ['cosmos', 'persimmon', 'ginkgo', 'maple', 'high autumn sky'],
    11: ['maple', 'ginkgo', 'sasanqua', 'persimmon', 'fallen leaves'],
    12: ['camellia', 'nandina', 'first snow', 'bare tree', 'lantern'],
}

issues = []
sig_over = []
funnel_ref = []
def ng(nid, *m): issues.append(f'{nid}: ' + ' '.join(str(x) for x in m))


def md2html(md):
    """rules/note.md の HTML 規約：<p> <hr> <h2> <br> <strong>、タグ間に改行を入れない"""
    def inline(s): return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    out = []
    for block in md.split('\n\n'):
        b = block.strip()
        if not b: continue
        if b == '---': out.append('<hr>'); continue
        if b.startswith('## '): out.append('<h2>' + inline(b[3:].strip()) + '</h2>'); continue
        lines = [l.strip() for l in b.split('\n') if l.strip()]
        out.append('<p>' + '<br>'.join(inline(l) for l in lines) + '</p>')
    return ''.join(out)


def being_section(md, i, push):
    """在り方署名の段＝「あわせて読む」の手前・背中押しの直前にある、最後の --- 以降"""
    if i <= 0: return ''
    head = md[:i]
    first = re.split(r'[\n　 ]+', push.strip())[0] if push else ''
    j = head.rfind(first) if first else -1
    return head[:j if j > 0 else len(head)].rsplit('\n---\n', 1)[-1].strip()


def being_open(md, i, push):
    """在り方署名の書き出し＝背中押しの直前のブロックの一行目"""
    if i <= 0: return ''
    head = md[:i]
    first = re.split(r'[\n\u3000 ]+', push.strip())[0] if push else ''
    j = head.rfind(first) if first else -1
    blocks = [b.strip() for b in head[:j if j > 0 else len(head)].split('\n\n') if b.strip() and b.strip() != '---']
    return blocks[-1].split('\n')[0] if blocks else ''


def load_titles():
    ts = set()
    for f in glob.glob(os.path.join(REPO, 'notes', '**', 'note_*.json'), recursive=True):
        try: d = json.load(open(f, encoding='utf-8'))
        except Exception: continue
        if 'title' in d: ts.add(d['title'].lstrip('💼💗'))
    return ts


def check(d, path, titles):
    nid = d.get('date', os.path.basename(path))
    md = d.get('content_markdown', '')
    if not md:
        ng(nid, 'content_markdown が空'); return None
    plan = d.get('platform_origin')
    # 記事タイトルの引用は原表記のまま（恒久ルールの例外）
    naked = md
    for t in titles:
        if '私' in t: naked = naked.replace(t, '')

    # 1 禁止語（原理01/07の公式文言と、「」内の引用は例外）
    body = md.replace('今日決められることだけを渡す', '').replace('動ける範囲を渡す', '')
    body = re.sub(r'「[^」]*」', '', body)   # 読者の声・過去記事タイトルの引用内は文体ルールの対象外
    hit = [w for w in BANNED if w in body]
    if hit: ng(nid, '禁止語', '／'.join(hit))
    watasu = len(re.findall(WATASU_RE, body))   # 参考カウント（比喩かどうかは目視）

    # 2 一人称
    p = len(re.findall(r'(?<![私])私(?!たち)', naked))
    if p: ng(nid, f'一人称の「私」が{p}箇所（正は「わたし」）')

    # 3 md と html の同期
    if 'content_html' in d and md2html(md) != d['content_html']:
        ng(nid, 'content_markdown と content_html がずれている')

    # 4 プラン記号
    if plan in PLAN and d.get('source_week') != 'standing_guide':
        if not d.get('title', '').startswith(PLAN[plan]):
            ng(nid, f'タイトルの先頭に {PLAN[plan]} がない（{plan}由来）')
    if re.search(r'(💼|💗)\1', d.get('title', '')): ng(nid, 'プラン記号が二重になっている')

    # 5 定番プロミス
    if PROMISE not in md: ng(nid, '定番プロミスがない')
    if re.search(r'月\s*\d+\s*本', md): ng(nid, '本数の約束が残っている（達成できない月に嘘になる）')

    # 5-2 本文の最終行はメンバーシップURL（rules/note.md）
    if md.rstrip().split('\n')[-1].strip() != MEMBERSHIP_URL:
        ng(nid, f'本文の最終行がメンバーシップURLでない（読み終わった場所に入口がない）: 「{md.rstrip().split(chr(10))[-1].strip()[:28]}」')

    # 6 在り方署名 → 背中押し → あわせて読む の順
    i = md.find('あわせて読む')
    if i < 0:
        ng(nid, '「あわせて読む」がない')
    else:
        push = d.get('closing_push')
        if not push:
            ng(nid, 'closing_push が空（テーマ固有の一言＋背中押しの二段）')
        else:
            miss = [l.strip() for l in re.split(r'[\n\u3000 ]+(?=[^、。])', push) if l.strip() and l.strip() not in md[:i]]
            if miss: ng(nid, 'closing_push が本文の「あわせて読む」より前にない:', '／'.join(m[:24] for m in miss))

    # 7 有料エリアの境界と比率
    vis = d.get('visibility')
    if vis == 'members_only':
        j = md.find(PAYWALL)
        if j < 0:
            ng(nid, '本文に有料エリアの境界がない（note.comでどこに有料ラインを置くか分からない）')
        else:
            r = md.rfind('---', 0, j) / len(md)
            if abs(r - float(d.get('free_ratio', 0))) > 0.02:
                ng(nid, f'free_ratio が実測とずれている（記載 {d.get("free_ratio")} / 実測 {r:.2f}）')
            if '手に入るもの' in md[j:] or 'ここで得られること' in md[j:]:
                ng(nid, '販売リストが有料側に埋まっている（入会を決める材料が会員にしか見えない）')
        if d.get('price') not in (None, '', '0'):
            ng(nid, f'メンバーシップ限定なのに price={d.get("price")}')
    elif vis == 'public':
        if PAYWALL in md: ng(nid, '無料公開なのに有料エリアの境界が残っている')
    elif vis == 'single_paid':
        ng(nid, f'単発有料（{d.get("price")}円）。メンバーシップ月額と同額なら入会の判断を壊す')

    # 8 あわせて読むのプラン跨ぎ
    for t in d.get('internal_links', []):
        for f in glob.glob(os.path.join(REPO, 'notes', 'note_*.json')):
            o = json.load(open(f, encoding='utf-8'))
            if o.get('title', '').lstrip('💼💗') == t.lstrip('💼💗'):
                # 自分が both（両プランの土台）なら、どちらのプランへ張ってもよい
                if plan != 'both' and o.get('platform_origin') not in (plan, 'both', None) \
                        and o.get('source_week') != 'standing_guide':
                    ng(nid, f'あわせて読むがプラン跨ぎ: 「{t[:24]}」')
                break

    # 9 許可数字
    for m in re.finditer(r'[0-9０-９]+\s*(万|億|人|名|年|％|%)', md):
        seg = md[max(0, m.start() - 12):m.end()]
        if not any(n in seg for n in NUMS) and '1,500' not in seg and '1500' not in seg:
            pass  # 一般の数え上げ（三日・二人など）は対象外

    # 10 画像プロンプト
    ip = d.get('image_prompt', '') or ''
    if ip:
        c = [w for w in CANVA_NG if w in ip]
        if c: ng(nid, 'Canvaの禁止語', '／'.join(c))
        if '1280x670' not in ip: ng(nid, '画像プロンプトに横長1280x670の指定がない')
        if 'in her early thirties' not in ip: ng(nid, '画像プロンプトに in her early thirties がない')
        if 'No text' not in ip: ng(nid, '画像プロンプトが No text で締められていない')
        if 'central third' not in ip: ng(nid, '横の中央3分の1に全キャラを収める指定がない')
        if not d.get('image_prompt_short'): ng(nid, 'image_prompt_short がない')
        y, mth, day = [int(x) for x in (d.get('date') or '2026-01-01').split('-')]
        ok = list(MONTH_MOTIF[mth])
        if day <= 5: ok += MONTH_MOTIF[12 if mth == 1 else mth - 1]
        if day >= 26: ok += MONTH_MOTIF[1 if mth == 12 else mth + 1]
        if not any(k in ip.lower() for k in ok):
            ng(nid, f'季節モチーフが公開月（{mth}月）と合っていない：{MONTH_MOTIF[mth]}')
    return {'nid': nid, 'plan': plan, 'watasu': watasu, 'push': (d.get('closing_push') or '').split('\n')[-1],
            'file': os.path.basename(path),
            'targets': d.get('funnel_targets') or [],
            'promise_map': d.get('promise_map'),
            'heads': re.findall(r'^##+\s*(.+?)\s*$', md, re.M),
            'leads': re.findall(r'^(.+)\n→「', md[i:], re.M) if i > 0 else [],
            'being': being_open(md, i, d.get('closing_push') or ''),
            'sig_fixed': 'でしかない' in being_section(md, i, d.get('closing_push') or ''),
            'week': d.get('source_week') or ''}


def promise_parts(reply):
    """funnel返信の約束を、回収すべき単位に割る。
    形は決まっている：「〜をnoteに書きました」。『と、』が単位の区切り。"""
    m = re.search(r'^(.*)を、?\s*note\s*に書きました', reply)
    if not m: return []
    return [p.strip() for p in m.group(1).split('と、') if p.strip()]


def funnel_check(rows):
    """約束と回収の突き合わせ（2026-08-31 Coco決定・恒久ルール）

    funnel投稿の返信2で「AとBをnoteに書きました」と約束したら、note側は
    `promise_map` で「どの見出しでAを回収し、どの見出しでBを回収したか」を明示する。
    機械が見るのは**構造**だけ——約束の写しが投稿と一致するか、挙げた見出しが実在するか。
    意味が本当に回収できているかは目視だが、**書けないなら回収していない**ので、
    書かせること自体が空手形を止める。

    背景：2026-08-31 のWチェックで、9/1週の funnel 8本のうち4本（th_03・th_06・th_07・x_10）が
    約束の半分を書かずに公開待ちになっていた。3つのツールはどれも自分のファイルしか読まないため、
    投稿とnoteをまたぐこの穴は構造的に検出できなかった。
    """
    # standing_guide（常設案内）と type_guide（型の道案内）は週に紐づかず funnel も持たない
    weeks = {r['week'] for r in rows if r['week'] and r['week'] not in ('standing_guide', 'type_guide')}
    # 複数週をまとめて見るとき（--all）は参考出力にする。配信済みの週には遡及しない（CLAUDE.md）
    single = len(weeks) == 1
    out = ng if single else (lambda nid, *m: funnel_ref.append(f'{nid}: ' + ' '.join(str(x) for x in m)))
    for wk in sorted(weeks):
        wp = os.path.join(REPO, 'posts', f'week_{wk.replace("-", "_")}.json')
        if not os.path.exists(wp):
            # 配信から30日で posts/ は消える（rules/ops.md）。過去週で無いのは正常なので黙る。
            # 今まさに見ている1週だけは、無いこと自体が事故なので言う
            if single:
                print(f'  ! {wk}: 35投稿のファイルが無く、約束の突き合わせを回せない（{os.path.basename(wp)}）')
            continue
        posts = json.load(open(wp, encoding='utf-8')).get('posts', [])
        for p in posts:
            if not p.get('note_funnel'): continue
            reply = (p.get('self_replies') or [''])[-1]
            parts = promise_parts(reply)
            if not parts:
                out(p['id'], 'funnel返信2から約束を取り出せない（「〜をnoteに書きました」の形にする）')
                continue
            hit = [r for r in rows if p['id'] in r['targets']]
            if not hit:
                out(p['id'], f'約束したnoteが無い（空手形）: {" ／ ".join(parts)}')
                continue
            for r in hit:
                pm = r['promise_map']
                if not isinstance(pm, dict) or not pm:
                    out(r['nid'], f'promise_map が無い（{p["id"]} の約束 {len(parts)}件をどの見出しで回収したか書く）')
                    continue
                if set(pm) != set(parts):
                    miss = [x for x in parts if x not in pm]
                    extra = [x for x in pm if x not in parts]
                    if miss: out(r['nid'], f'{p["id"]} の約束が promise_map に無い: ' + ' ／ '.join(miss))
                    if extra: out(r['nid'], f'promise_map に投稿の約束と違う項目: ' + ' ／ '.join(extra))
                for k, v in pm.items():
                    if v not in r['heads']:
                        out(r['nid'], f'promise_map「{k}」が指す見出し「{v}」が本文に無い')


def main(paths):
    titles = load_titles()
    rows = []
    for path in paths:
        d = json.load(open(path, encoding='utf-8'))
        if 'title' not in d: continue
        r = check(d, path, titles)
        if r: rows.append(r)
    print(f'=== 機械チェック: note {len(rows)}本 ===\n')

    # 週内の重複（背中押しの言い切り／あわせて読むの導入文／在り方署名の書き出し）
    for key, name, lim in (('push', '背中押しの言い切り', 1), ('being', '在り方署名の書き出し', 1)):
        c = collections.Counter(r[key] for r in rows if r[key])
        dup = [k for k, v in c.items() if v > lim]
        if dup: ng('週内', f'{name}が重複: ' + ' / '.join(x[:28] for x in dup))
    # 在り方署名の①定型は週3本まで（広い定義＝語尾「でしかない」で締めるものを全部数える）
    # 週ごとに数える。--all で全記事をまとめて数えない。過去分・常設案内は週の単位を持たないので対象外
    # 配信済みの週には遡及しないので、--all では要修正にせず参考として出す
    weeks = sorted({r['week'] for r in rows if r['week'] and r['week'] != 'standing_guide'})
    for wk in weeks:
        grp = [r for r in rows if r['week'] == wk]
        fixed = [r['nid'] for r in grp if r.get('sig_fixed')]
        if len(grp) >= 7 and len(fixed) > 3:
            msg = f'在り方署名の定型（〜でしかない）が{len(fixed)}本（上限3本）: ' + ' / '.join(fixed)
            if len(weeks) == 1: ng(wk, msg)
            else: sig_over.append(f'{wk}: {msg}')

    funnel_check(rows)

    lead = collections.Counter(l for r in rows for l in r['leads'])
    dup = [k for k, v in lead.items() if v > 1]
    if dup: ng('週内', 'あわせて読むの導入文が重複: ' + ' / '.join(x[:28] for x in dup[:4]))

    if issues:
        print(f'■ 機械チェック: 要修正 {len(issues)}件')
        for i in issues: print('  -', i)
    else:
        print('■ 機械チェック: 要修正 0件')

    c = collections.Counter(r['plan'] for r in rows)
    print(f'\n■ 参考カウント\n  プラン別: {dict(c)}')
    w = [(r['nid'], r['watasu']) for r in rows if r.get('watasu')]
    if w:
        print(f'  「渡す/渡し」候補: {sum(n for _, n in w)}箇所 / {len(w)}本 {w}')
        print('    ※禁止しているのは**比喩的な用法**だけ（言う／頼む／話す／送る／伝える に置換）。')
        print('    　仕事や物を実際に渡す記述は対象外。**比喩かどうかは目視で決める**')
    for m in funnel_ref:
        print(f'  ! 約束と回収: {m}')
    if funnel_ref:
        print('    （複数週をまとめて見ているので参考。配信済みの週には遡及しない。'
              '直すのは、その週を --week で見たとき）')
    for m in sig_over:
        print(f'  ! {m}\n    （配信済みの週は遡及しない。note_fix_queue の deferred 済み）')

    print('\n' + '=' * 60)
    print('【判断チェック】機械では判定できない。必ず目視で埋めること')
    print('=' * 60)
    # 条件の正典は rules/note.md ①ブランド整合性チェック（＝rules/check.md ⑥-1 と同じ形）。
    # ここに条文を書き写さない。2026-09-03：旧版は「商品名の枠内か」と出していたが、
    # 商品名で合否を出さないことは 2026-08-31 に決まっていた（判定は約束・軸・売り物の3層）。
    # 「在り方（Being）に着地」も、Being を売り物と読ませない形へ直した（CLAUDE.md 3層表）。
    print('① ブランド整合性 — 約束・軸・売り物の3層の枠内か（CLAUDE.md 収益モデル節。商品名で合否を出さない）。')
    print('   分けるのはドメイン。X由来＝組織と仕事／Threads由来＝恋愛と関係（軸で媒体を分けない）。')
    print('   Xの立ち位置が「翻訳者」になっているか（切って捨てる側に寄っていないか）。')
    print('   やり方（How）の羅列で終わらず、在り方（Being）に着地しているか')
    print('   （Beingは書き手の内側の軸。読者に出す売り物の言葉は「決めていい、と言ってくれる場所。」）')
    print('② 到達力 — タイトルが「短い断定 × 現場の痛み」の二層か。冒頭2〜3行で痛みの名指しがあるか。')
    print('   保存・シェアの引き金が最低1つあるか。その週に「覗き見型」のタイトルが1本あるか')
    print('③ 読了と納得 — ターゲットの8割が読み切れる構造か。読後に残るのが情報ではなく')
    print('   「整理された感覚」か。同じ形の悩みが来たとき自分で処理できる手触りが残るか')
    print('④ 6項目 — ①向いているか ②何が変わるか ③変化までどれくらい（固定スロット）')
    print('   ④自分でやること1つ ⑤費用 ⑥どんな場面に合わないか（固定スロット）')
    print('\n■ 在り方署名の書き出し（記事ごとに違う角度になっているか目視／● ＝ ①定型・週3本まで）')
    for r in rows: print(f'  {"●" if r.get("sig_fixed") else "　"} {r["nid"]} {r["being"][:50]}')
    print('\n■ 背中押しの言い切り（週内で重複していないか目視）')
    for r in rows: print(f'  {r["nid"]} {r["push"][:52]}')
    return 1 if issues else 0


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(2)
    if a[0] == '--all':
        fs = sorted(glob.glob(os.path.join(REPO, 'notes', 'note_*.json')))
    elif a[0] == '--week':
        fs = [f for f in sorted(glob.glob(os.path.join(REPO, 'notes', 'note_*.json')))
              if json.load(open(f, encoding='utf-8')).get('source_week') == a[1]]
    else:
        fs = [f for x in a for f in sorted(glob.glob(x))]
    sys.exit(main(fs))
