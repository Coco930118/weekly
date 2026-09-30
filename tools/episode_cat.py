#!/usr/bin/env python3
"""在庫のカテゴリが空の素材に、語彙から 💼組織 / 💗恋愛 を振る。

■ なぜ要るか
  `reference/episodes_soshiki.json` は 2026-09-30 時点で **232件が category 空**
  （在庫の3分の1）。本文を読めば分かるので困らないが、**「今週は組織の在庫が薄い」
  のような配分の判断をするとき、3分の1が数に入らない**。

■ 方針（2026-09-30 Coco決定）
  **誤って振るほうが、空のままより害が大きい。** だから——
  - **確実に割れるものだけ振る。** 迷うものは**空のまま残す**
  - **本文（theme・key_phrases・title）は一文字も触らない。** 足すのは category だけ
  - 判定は**語彙のスコア差**。どちらかが `MIN_HITS` 以上、かつ相手の `RATIO` 倍以上のときだけ振る

■ 使い方
    python3 tools/episode_cat.py            # 下見（書き込まない）
    python3 tools/episode_cat.py --apply    # 書き込む
    python3 tools/episode_cat.py --show 20  # 判定の内訳を20件出す

■ 語彙はここが正典（`rules/source.md` の在庫ルールとは別の、機械の都合の表）
  ⚠️ **両方に出る語（お客様・距離・気持ち・LINE・友達）は数えない。** 入れると全部が
  組織側に倒れる（2026-09-30 実測：お客様を入れると恋愛側の判定が 31件→9件 に落ちた）
"""
import json, os, sys, re

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, '..', 'reference', 'episodes_soshiki.json')

SOSHIKI = ['店長', '上司', '部下', 'スタッフ', '会社', '社長', '部門', '業界', '単価',
           '売上', '原価', '人事', '面接', '議事録', 'シフト', '勤怠', 'チーム', '社員',
           '報告', '指示', '権限', '委譲', '現場', '営業', '職場', '退職', '辞め',
           '評価', '会議', 'ミーティング', '教育', '育成', '経営', '店舗', '部署']
KANKEI  = ['お相手さま', '大切な人', '彼氏', '彼女', '恋', '好きな人', '別れ', '既読',
           'デート', '結婚', '夫', '妻', '付き合', '音信不通', '片思い', '浮気', '嫉妬',
           '愛', '恋愛', '同棲', 'プロポーズ', '夫婦', '子育て', '実家', '親']
# 両方に出る語。数えない（上の docstring 参照）
NEUTRAL = ['お客様', '距離', '気持ち', 'LINE', '友達', '仲間', '連絡', '相手', '家族']

MIN_HITS = 2      # 勝ち側の最低ヒット数
RATIO    = 2.0    # 勝ち側 ÷ 負け側 がこれ以上のときだけ振る


def load():
    d = json.load(open(PATH, encoding='utf-8'))
    key = 'episodes' if 'episodes' in d else 'items'
    return d, key


def blob(e):
    parts = [str(e.get('title', '')), str(e.get('theme', ''))]
    kp = e.get('key_phrases') or e.get('key_phrase') or []
    parts.append(' '.join(kp) if isinstance(kp, list) else str(kp))
    return ' '.join(parts)


def score(text):
    s = sum(text.count(w) for w in SOSHIKI)
    k = sum(text.count(w) for w in KANKEI)
    return s, k


def decide(s, k):
    if s >= MIN_HITS and s >= k * RATIO:
        return '組織と仕事'
    if k >= MIN_HITS and k >= s * RATIO:
        return '恋愛と関係'
    return None


def main():
    apply_ = '--apply' in sys.argv
    show = 0
    if '--show' in sys.argv:
        i = sys.argv.index('--show')
        show = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 10

    d, key = load()
    eps = d[key]

    # 表記ゆれを先にそろえる（「組織・仕事」→「組織と仕事」）
    fixed = 0
    for e in eps:
        if (e.get('category') or '').strip() == '組織・仕事':
            e['category'] = '組織と仕事'
            fixed += 1

    # E1〜E200 は、この台帳が「組織掌握の実録素材集」として作られた 1.0 の初期バッチ
    # （ヘッダーの title / theme / description / tags がすべて組織）。category という欄が
    # できる前の分なので空になっているだけで、**中身は組織。語彙で推測しない**
    # 実測 2026-09-30：E1-100 と E101-200 は 200件すべてが空。E201 以降は恋愛が混ざる
    ORIG_BATCH = 200
    orig = 0
    for e in eps:
        n = e['id'][1:]
        if not n.isdigit() or int(n) > ORIG_BATCH:
            continue
        if (e.get('category') or '').strip():
            continue
        if apply_:
            e['category'] = '組織と仕事'
        orig += 1

    blanks = [e for e in eps if not (e.get('category') or '').strip()
              and not (e['id'][1:].isdigit() and int(e['id'][1:]) <= ORIG_BATCH)]
    hit_s = hit_k = skip = 0
    shown = 0
    for e in blanks:
        s, k = score(blob(e))
        cat = decide(s, k)
        if show and shown < show:
            print(f"  {e['id']:6} 組織{s:2} 恋愛{k:2} → {cat or '（空のまま）'}　{str(e.get('title',''))[:34]}")
            shown += 1
        if cat is None:
            skip += 1
            continue
        if apply_:
            e['category'] = cat
        if cat == '組織と仕事':
            hit_s += 1
        else:
            hit_k += 1

    print(f"\n■ 表記ゆれ「組織・仕事」→「組織と仕事」 {fixed}件")
    print(f"■ E1〜E{ORIG_BATCH}（1.0 の組織バッチ・出どころで確定） {orig}件 → 組織と仕事")
    print(f"■ 未分類 {len(blanks)}件 → 組織 {hit_s}件 ／ 恋愛 {hit_k}件 ／ **空のまま {skip}件**")
    if apply_:
        with open(PATH, 'w', encoding='utf-8') as f:
            f.write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
        print("  書き込んだ（本文は触っていない。足したのは category だけ）")
    else:
        print("  下見だけ。書き込むには --apply")
    return 0


if __name__ == '__main__':
    sys.exit(main())
