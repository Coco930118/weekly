#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""各媒体のプロフィール文面の検査（reference/brand_profile.json）

使い方:  python3 tools/profile_check.py

【なぜ別ツールか】プロフィールは**どのツールの対象でもなかった**。
full_check は posts/、note_check は notes/、shindan_check は診断、
episode_check は素材しか見ない。**いちばん人目に触れる4行が、一度も検査されていない。**
2026-09-02 のWチェックで、Xのプロフィールに禁止語が2語（「設計」×2・「渡し」×1）
入ったまま公開されているのが、手で読んで初めて見つかった。

禁止語の定義は full_check.py から**インポートする**。ここに複製を置かない
（rules/check.md「全媒体ルールは CLAUDE.md にだけ置く」＝同じ主題を2箇所に書いたら、
それは片方が古くなる予約をしたのと同じ）。
"""
import json, re, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from full_check import BANNED, BANNED_RE          # 定義は1箇所。ここに複製しない

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(REPO, 'reference', 'brand_profile.json')

# 「延べ5万人を超える」で固定（CLAUDE.md「使える数字は4つだけ」）。
# 「約」と「超」は逆の意味なので同時に使わない。下は誤りの表記だけを並べる
NUM_NG = ['約5万人', '5万人超', '5万人以上', '五万人', '約5万']
# ひとことの絵文字（X＝💎／Threads＝🫶）は2026-08-24に廃止された。
# ただし**射程は投稿の quote**（rules/posts.md）で、プロフィールは対象外。
# 参考として出すだけ——廃止した記号を看板で使い続けているかは、目で決める
RETIRED = ['💎', '🫶']

issues = []
def ng(who, *m): issues.append(f'{who}: ' + ' '.join(str(x) for x in m))


def main():
    d = json.load(open(PROFILE, encoding='utf-8'))
    rows = []
    for name, v in d.get('platforms', {}).items():
        t = v.get('profile_text')
        if not t: continue
        # 運用対象外の媒体は検査しない（brand_profile.json の meta が決めている）
        if v.get('in_scope') is False:
            rows.append((name, t, True)); continue
        rows.append((name, t, False))

        naked = re.sub(r'「[^」]*」', '', t)        # 「」内の引用は文体ルールの対象外
        hit = [w for w in BANNED if w in naked]
        hit += sorted({m for r in BANNED_RE for m in re.findall(r, naked)})
        if hit: ng(name, '禁止語', '／'.join(hit))

        bad = [w for w in NUM_NG if w in t]
        if bad: ng(name, '数字の表記が誤り', '／'.join(bad), '（正は「延べ5万人を超える」）')

    print('=== 機械チェック: プロフィール ===\n')
    for name, t, skipped in rows:
        mark = '（運用対象外・検査しない）' if skipped else ''
        print(f'  {name} {len(t)}字 {mark}')
    print()
    if issues:
        print(f'■ 機械チェック: 要修正 {len(issues)}件')
        for i in issues: print('  -', i)
    else:
        print('■ 機械チェック: 要修正 0件')

    ref = [(n, [e for e in RETIRED if e in t]) for n, t, s in rows if not s]
    ref = [(n, e) for n, e in ref if e]
    if ref:
        print('\n■ 参考カウント')
        for n, e in ref:
            print(f'  廃止した絵文字が {n} のプロフィールにある: {"／".join(e)}')
        print('    ※2026-08-24 に廃止したのは**投稿のひとことの絵文字**で、プロフィールは射程外。')
        print('    　違反ではない。**看板で使い続けるかは目で決める**')

    print('\n' + '=' * 60)
    print('【判断チェック】機械では判定できない。必ず目視で埋めること')
    print('=' * 60)
    # ⚠️ 旧版「1行目で『誰向けか』が分かるか」は削除した（2026-09-02 同日）。
    # 宛名（「〜人へ」）を求める文で、原理04（決断を相手に返す）と
    # ゼロ主語（rules/posts.md）の両方とぶつかっていた。同日の Coco 判断で
    # 1行目は「結果」に変わっている
    print('① 1行目が「結果」になっているか — いまの状態でも宛名でもなく、読んだ先に何が起きるか。')
    print('   宛名（「〜人へ」）は読者の席を埋めてしまう（原理04・ゼロ主語）')
    print('② 権威の数字が、いまの母数と釣り合っているか — フォロワーが2桁のうちは')
    print('   「延べ5万人」が自己申告に見える。下ろす判断は CLAUDE.md「使える数字」の枠内で行う')
    print('③ 3層（約束／軸／売り物）の枠内か — 正典は CLAUDE.md 収益モデル節')
    print('④ 特定回避の例外の条件4つを守っているか（店舗名・地域・在籍時期・現在の勤務先を出さない）')
    return 1 if issues else 0


if __name__ == '__main__':
    sys.exit(main())
