#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""週35投稿の恒久ルール全チェック（2026-08-24 Coco承認・固定ツール）

使い方:  python3 tools/full_check.py posts/week_YYYY_MM_DD_YYYY_MM_DD.json

【重要】このスクリプトは「機械で検出できるルール」だけを見る。
判断が要るルール（処方の言い換え重複／原理配分／8割読み切り／比喩一本化／
ブランド整合性）は自動判定できないため、末尾に「判断チェック用の出力」を出す。
Claudeはこの出力を使って必ず目視で埋めること。機械チェックだけで
「全項目クリア」と報告してはいけない（実際にそれで重複を3回見逃した）。
"""
import json, re, sys, collections, datetime, glob, os

BANNED = ['設計', '構造', '体制', '仕組み', '熱量', '消耗', '削れる', '明け渡す',
          '渡す', '渡し', '恋人', '寄り添', 'んです', 'と言えるでしょう', 'いかがでしょうか', '台所']
CTX = ['夫婦', '子ども', '友達', 'ママ友', '義理', 'お相手さま', '好き', '気にな', '大切な人',
       'パートナー', '恋愛', '親友', '家族', 'あの人', '隣にいる人', '遠距離', '片思い', '親子', '別れ', '夫', '妻', '彼']
SOSHIKI = ['部下', '上司', '現場', 'チーム', '会議', '職場', '売上']
NUMS = ['20年', '5万人', '40名', '月商']
PROMISE = 'メンバーシップは、毎週深堀りが増えて'
TIME_WORDS = ['今夜', '今晩', '今朝', '夕方', 'この時間', '寝る前', '翌朝', '店じまい',
              '金曜の夜', '土曜の夜', '日曜の夜', '月曜の夜', '土曜の朝', '日曜の朝', '月曜の朝']
ANGLES = ['front bust-up', 'side-profile', 'looking up', 'over-the-shoulder', 'close-up']
WIT_HINTS = ['お茶', 'アイス', 'おいしいもの', 'プリン', '花を', '春巻き', 'ビール', 'レモンサワー',
             'コーヒー', '昼寝', '湯船', '温泉', '麦茶', '寝ていい', '休みの人', 'それだけ。',
             'ごはん', '元手', 'シーツ', '一杯', '取り返す']

issues = []
def ng(pid, *msg):
    issues.append(f'{pid}: ' + ' '.join(str(m) for m in msg))

def band(hh):
    return 'morning' if hh < 12 else ('evening' if hh < 21 else 'night')

def main(path):
    d = json.load(open(path, encoding='utf-8'))
    posts = d['posts']
    X = [p for p in posts if p['platform'] == 'X']
    TH = [p for p in posts if p['platform'] == 'Threads']
    print(f'=== 機械チェック: {os.path.basename(path)} （X {len(X)} / Threads {len(TH)}）===\n')

    # 1 禁止語（本文・ひとこと・返信を横断）
    STYLE_ONLY = ['んです', 'と言えるでしょう', 'いかがでしょうか', '寄り添']
    for p in posts:
        t = p['content'] + p.get('quote', '') + ' '.join(p.get('self_replies', []))
        naked = re.sub(r'「[^」]*」', '', t)  # 読者の声の引用内は文体ルールの対象外
        hit = [w for w in BANNED if (w in naked if w in STYLE_ONLY else w in t)]
        if hit: ng(p['id'], '禁止語', hit)

    # 2 X形式
    for p in X:
        l1 = p['content'].split('\n')[0]
        last = p['content'].strip().split('\n')[-1]
        naked = re.sub(r'「[^」]*」', '', p['content'])
        if not l1.startswith('「'): ng(p['id'], '1行目が読者の声引用でない')
        if last.rstrip().endswith(('？', '?', 'ですか。')): ng(p['id'], '末尾が明示質問')
        if '私' in naked: ng(p['id'], '一人称「私」（わたしに統一）')
        if '💎' in p.get('quote', ''): ng(p['id'], 'quoteに💎（絵文字は2026-08-24廃止）')
        lines = [l for l in p['content'].split('\n') if l.strip()]
        if len(lines) > 7: ng(p['id'], f'X本文が{len(lines)}行（5〜7行に圧縮する）')

    # 3 Threads形式
    for p in TH:
        last = p['content'].strip().split('\n')[-1]
        body = p['content'].split('感情はある。')[0].strip()
        n = len(body.replace('\n', ''))
        if '感情はある。依存はしない。' not in last or '💍' not in last:
            ng(p['id'], 'タグライン締めなし')
        if not any(w in p['content'] for w in CTX): ng(p['id'], '恋愛/関係の文脈明示なし')
        s = [w for w in SOSHIKI if w in p['content']]
        if s: ng(p['id'], '組織語', s)
        if not (80 <= n <= 190): ng(p['id'], f'字数 {n}')
        q = p.get('quote', '').rstrip('🫶💎').strip()
        if q and q == p['content'].split('\n')[0].strip(): ng(p['id'], 'quoteが冒頭文の流用')
        if '🫶' in p.get('quote', ''): ng(p['id'], 'quoteに🫶（絵文字は2026-08-24廃止）')

    # 4 数字
    used = []
    for p in posts:
        for num in NUMS:
            if num in p['content']:
                lines = [l for l in p['content'].split('\n') if l.strip()]
                pos = next(i for i, l in enumerate(lines) if num in l)
                used.append((p['id'], num))
                if pos < 2: ng(p['id'], f'数字{num}が{pos+1}行目（1〜2行目禁止）')
    if len(used) > 3: ng('WEEK', '許可数字が週3本超', used)

    # 5 funnel
    fun = [p for p in posts if p.get('note_funnel')]
    if len(fun) != 8: ng('WEEK', f'funnel {len(fun)}本（規定8本）')
    for p in fun:
        r = p.get('self_replies', [])
        if not (len(r) >= 2 and PROMISE in r[-1]): ng(p['id'], 'funnel返信2に定番プロミスなし')
        wd = datetime.date(*map(int, p['date'].split('-'))).weekday()
        if wd >= 5:
            mark = '（Xの曜日ネタなら例外・要目視）' if p['platform'] == 'X' else ''
            ng(p['id'], f'funnelが土日配置（{p["date"]}）{mark}')
    for p in posts:
        if not p.get('note_funnel') and ('noteに' in p['content'] or 'プロフィール' in p['content']):
            ng(p['id'], '非funnelにnote/プロフィール誘導')

    # 6 構文重複
    for label, arr in [('X', X), ('Th', TH)]:
        yame = [p['id'] for p in arr if re.search(r'(やめる|やめてみる|やめた)。?.$', p.get('quote', ''))]
        if len(yame) > 2: ng('WEEK', f'{label} quote「やめる」型 {len(yame)}本', yame)
    ab = [p['id'] for p in TH if re.search(r'[^\n]+でも、[^\n]+でも。|[^\n]+にも、[^\n]+にも。', p['content'])]
    if len(ab) > 5: ng('WEEK', f'「AでもBでも」構文 {len(ab)}本（上限5）', ab)
    heads = collections.Counter()
    for p in TH:
        l1 = p['content'].split('\n')[0]
        heads['わたしは〜' if l1.startswith('わたしは') else ('「」引用' if l1.startswith('「') else 'その他')] += 1
    if heads.get('わたしは〜', 0) >= 3:
        ng('WEEK', f'Threads冒頭「わたしは、〜することにしてる」が{heads["わたしは〜"]}本（例文構文は週3本未満）')
    uke = collections.Counter(re.findall(
        r'(って相談があった|って聞かれることがある|そう打ち明けられたことがある|って、この前も聞かれた|'
        r'という声を、何度も聞いてきた|って話を聞いた|って相談を受けたことがある)', ''.join(p['content'] for p in posts)))
    for k, v in uke.items():
        if v >= 3: ng('WEEK', f'受け口「{k}」が{v}回（週3本未満に）')
    # 伝聞マーカーの偏り（相談者目線の入り方が同じ形に寄っていないか）
    den = collections.Counter()
    for p in TH:
        l1 = p['content'].split('\n')[0]
        m = re.search(r'(人がいる。|人がいた。|そう。|んだって。|みたい。|って。|ことがある。|話を聞いた。)$', l1)
        if m: den[m.group(1)] += 1
    for k, v in den.items():
        if v >= 3: ng('WEEK', f'冒頭の文末が「{k}」で{v}本（同じ形は週3本未満に散らす）')

    # 7 時間軸
    for p in posts:
        hh = int(p['time'][:2])
        b = band(hh)
        wdj = '月火水木金土日'[datetime.date(*map(int, p['date'].split('-'))).weekday()]
        self_ref = [f'{wdj}曜の朝', f'{wdj}曜の夜', '今朝'] if b == 'morning' else [f'{wdj}曜の夜', '今夜', '今晩']
        hits = [w for w in TIME_WORDS if w in p['content'] and w not in self_ref]
        if b == 'morning' and hits:
            fwd = any(k in p['content'] for k in ['今夜', '寝る前', '今晩'])
            past = any(k in p['content'] for k in ['夜があった', '翌朝', '昔は', 'だった', 'みたい', 'そう。', 'って'])
            if not (fwd or past): ng(p['id'], f'朝{p["time"]}に夜の語', hits, '（前方指示か過去形にする）')

    # 8 画像プロンプト
    ang = collections.Counter(); ani = collections.Counter(); prompts = []
    for p in posts:
        ip = p.get('image_prompt') or ''
        prompts.append(ip)
        if not ip: ng(p['id'], 'image_promptなし'); continue
        if 'early 30s' not in ip: ng(p['id'], '画像: early 30sなし')
        if 'No text' not in ip: ng(p['id'], '画像: No textなし')
        if 'elegant 40s woman' in ip: ng(p['id'], '画像: elegant 40s woman残存')
        if not any(a in ip for a in ['Shizuku', 'Shiratama', 'Hiyori']): ng(p['id'], '画像: 動物なし')
        if band(int(p['time'][:2])) not in ip: ng(p['id'], f'画像: 時間帯ズレ（{p["time"]}）')
        for a in ANGLES:
            if a in ip: ang[a] += 1; break
        ani[tuple(sorted(a for a in ['Shizuku', 'Shiratama', 'Hiyori'] if a in ip))] += 1
    if len(prompts) != len(set(prompts)): ng('WEEK', '画像プロンプトに重複')
    if sorted(ang.values()) != [7] * 5: ng('WEEK', 'アングル巡回が7本ずつでない', dict(ang))
    if sorted(ani.values()) != [5] * 7: ng('WEEK', '動物組合せが5本ずつでない', {'+'.join(k) or 'なし': v for k, v in ani.items()})

    # 9 肩の力と輝き
    wit = [p['id'] for p in posts if any(w in p['content'] for w in WIT_HINTS)]
    tatazumai = [p['id'] for p in TH if '感情はある。' in p['content'] and
                 not re.search(r'(してみる|してみた|やめてみ|決めて|入れて|聞いて|数え|書い)', p['content'].split('感情はある。')[0])]
    obs = [p['id'] for p in X if re.search(r'(それだけだ。|それだけの習慣だ。|ことにしてる。|してる。それだけ。)', p['content'][-60:])]
    if len(obs) > 4: ng('WEEK', f'X観察締めが{len(obs)}本（上限4）', obs)

    # 10 エピソード
    eids = [p.get('episode_id') for p in posts]
    if any(not e for e in eids): ng('WEEK', f'エピソード未紐づけ {sum(1 for e in eids if not e)}本')
    dup = [k for k, v in collections.Counter([e for e in eids if e]).items() if v > 1]
    if dup: ng('WEEK', 'エピソード重複', dup)
    try:
        log = json.load(open('reference/episode_usage_log.json', encoding='utf-8'))['log']
        last = {}
        wk = d.get('week', '')
        for l in log:
            r = l.get('episode_ref')
            if r and l.get('week') != wk:
                last[r] = max(last.get(r, ''), l.get('date', ''))
        for p in posts:
            e = p.get('episode_id')
            if not e: continue
            cut = (datetime.date(*map(int, p['date'].split('-'))) - datetime.timedelta(days=30)).isoformat()
            if last.get(e, '') >= cut: ng(p['id'], f'エピソード{e}は30日以内に使用済（{last[e]} / 基準{cut}）※在庫ゼロなら最終使用日が最も古いものから再使用可＝恒久ルール。その場合は報告に明示すること')
    except Exception as ex:
        print('  (使用ログ照合スキップ:', ex, ')')


    # 11 目線の一貫性（3型のどれか1秒で分かるか）＋ひとことの長さ
    DEN = ['って相談', 'って聞', 'って話', 'そう打ち明け', 'という声', 'みたい', 'だそう',
           'という人がいる', '人がいる', 'らしい', 'んだって', 'たって', 'そう。', '聞かれた', 'って笑ってた']
    for p in TH:
        body = p['content'].split('感情はある。')[0].strip()
        finals = [l for l in body.split('\n') if l.strip() and 'note' not in l]
        tail = finals[-1] if finals else ''
        if any(m in body for m in DEN): pov = '②相談者'
        elif 'わたし' in body or body.startswith('昔'): pov = '①わたし'
        elif re.search(r'(ある。|いる。|なる。|できる。|いい。|だ。|使える。|かもしれない。|なら。)$', tail): pov = '③観察'
        elif re.search(r'(た。|かった。|ていた。|だった。)$', tail): pov = '?曖昧'
        else: pov = '③観察'
        if pov == '?曖昧':
            ng(p['id'], '目線が曖昧（ゼロ主語＋過去形＝わたしの話に読まれる。伝聞マーカーか「昔は/わたしは」を付ける）')
    for p in posts:
        q = p.get('quote', '').rstrip('💎🫶').strip()
        if len(q) > 23:
            ng(p['id'], f'ひとことが{len(q)}字（上限23字・理想15〜20字。縦書き画像で読めなくなる）')

    # ===== 結果 =====
    if issues:
        print(f'■ 機械チェック: 要修正 {len(issues)}件')
        for i in issues: print('  -', i)
    else:
        print('■ 機械チェック: 要修正 0件')

    print(f'\n■ 参考カウント')
    print(f'  ウィット一滴 検出: {len(wit)}本 {wit}（目安5〜6）')
    print(f'  佇まい枠 候補: {len(tatazumai)}本 {tatazumai}（目安2〜3・要目視）')
    print(f'  X観察締め: {len(obs)}本 {obs}（上限4）')
    print(f'  funnel: {[p["id"] for p in fun]}')
    print(f'  許可数字: {used}')

    # ===== 判断チェック用の出力（ここを埋めないと完了にしない） =====
    print('\n' + '=' * 60)
    print('【判断チェック】以下はスクリプトでは判定できない。必ず目視で埋めること')
    print('=' * 60)
    print('\n① 処方の言い換え重複チェック — 各投稿の「今日の一手」を一行で書き出して並べ、')
    print('   語が違うだけの同じ処方が3本以上ないか確認する（語の検索では検出できない）')
    for p in posts:
        body = p['content'].split('感情はある。')[0].strip()
        lines = [l for l in body.split('\n') if l.strip()]
        tail = lines[-1] if lines else ''
        print(f'  {p["id"]}({p["platform"][:1]}) {tail[:46]}')
    print('\n② 原理配分チェック — 35本すべてに原理01〜07を割り当て、')
    print('   1プラットフォームで同じ原理が5本以上に偏っていないか数える（該当なしは書き直し）')
    print('\n③ そのほか目視項目：比喩一本化／再発パターン3型／8割読み切り／')
    print('   ブランド整合性（X=翻訳者・Threads=慈愛の哲学者）／佇まい枠の4点セット除外')
    return 1 if issues else 0

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    sys.exit(main(sys.argv[1]))
