#!/usr/bin/env python3
"""診断サイト（Coco930118/shindan）の結果画面コピーを、weekly の正典で検査する。

■ なぜ weekly 側に置くか
  条文の正典は shindan `CLAUDE.md` §3.65 だが、**検出語の正典は weekly**
  （`rules/posts.md`「抽象語を使わない」＋ `CLAUDE.md` 文体）。
  shindan 側は語を書き写すしかなく、weekly で語が増えるたびに古くなっていた
  （実測 2026-09-24：§3.65 の列挙と §0 の grep が、どちらも「戻す」「置かれる」を
  取りこぼしたまま止まっていた）。**語をここから直接読めば、写しが要らなくなる。**

■ 使い方
    SHINDAN_DIR=../shindan python3 tools/site_check.py          # 全週
    SHINDAN_DIR=../shindan python3 tools/site_check.py w12      # 週を指定

■ 見る範囲（§3.65 の対象・対象外をそのまま実装する）
  対象   = 結果画面に出る文字列（tag / punch / body / ans / cta / CENTER ほか）
  対象外 = 設問部（hook / q / 選択肢 t）……投稿と一字一句同じ制約があるため
           軸ラベル（distNames / tempNames / field）……仕様として固定
           コード注釈……読者に出ない
  見つけても設問部は直さない。**weekly の投稿側に報告する。**

■ 日付で切る語（ZAN・MODOSHI・OKU）の扱い
  ファイル名の週番号からは日付が引けないので、**この検査は日付で切らない。**
  古い週に出たものを直すかどうかは、`reference/todo.md`「【決着】結果画面の
  『残る／残す』」が正典。ここで判定しない。
"""
import os, re, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from full_check import BANNED, ZAN_RE, MODOSHI_RE, OKU_RE

SHINDAN = os.environ.get('SHINDAN_DIR', '../shindan')

# 「明け渡す」は距離軸の高い側の正式名称（shindan CLAUDE.md §3.65 対象外②）
ABST = [w for w in BANNED if w != '明け渡す']
# 「渡す／渡し」（full_check の BANNED_RE）は**投稿JSONの分だけ**（shindan CLAUDE.md §0）。
# 結果画面は「判断を渡す」が処方の動作語なので、ここでは当てない
# 設問部と軸ラベル。ここに出た語は報告するが「対象外」として分けて出す
SKIP_KEYS = {'hook', 'q', 't', 'distNames', 'tempNames', 'field', 'name'}
# 意図した例外。数えない（正典は rules/type.md「型のCTA一行」「橋渡しの一行」）
#   cta    ＝型のCTA8本（「残す」「戻す」を含む3本）
#   bridge ＝結果画面の「もう片方の軸へ渡す一行」。全型・全週で同じ固定文（「元に戻る」）
EXEMPT_KEYS = {'cta', 'bridge'}

LIT = re.compile(r'"((?:[^"\\]|\\.)*)"')
KEY = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?:\[\s*)?$')


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return '\n'.join(re.sub(r'//.*$', '', l) for l in src.split('\n'))


def hits(text):
    out = []
    out += [w for w in ABST if w in text]
    out += sorted(set(ZAN_RE.findall(text)))
    out += sorted(set(MODOSHI_RE.findall(text)))
    out += sorted(set(OKU_RE.findall(text)))
    return out


def scan(path):
    src = strip_comments(open(path, encoding='utf-8').read())
    rows = []
    for i, line in enumerate(src.split('\n'), 1):
        for m in LIT.finditer(line):
            lit = m.group(1)
            if not lit:
                continue
            k = KEY.search(line[:m.start()])
            key = k.group(1) if k else '?'
            naked = re.sub(r'「[^」]*」', '', lit)   # 「」内の引用は対象外
            h = hits(naked)
            if h:
                rows.append((i, key, sorted(set(h)), lit))
    return rows


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else None
    files = sorted(glob.glob(os.path.join(SHINDAN, 'kankei', 'data*.js')) +
                   glob.glob(os.path.join(SHINDAN, 'soshiki', 'data*.js')))
    if want:
        files = [f for f in files if want in os.path.basename(f)]
    if not files:
        print(f'data*.js が見つからない（SHINDAN_DIR={SHINDAN}）')
        return 1
    ng = skip = 0
    print('=== 機械チェック: 診断サイトの結果画面 ===')
    print(f'    検出語は weekly が正典（full_check の BANNED／ZAN／MODOSHI／OKU）。ここに写しを置かない\n')
    for f in files:
        rows = scan(f)
        if not rows:
            continue
        rel = os.path.relpath(f, SHINDAN)
        for i, key, h, lit in rows:
            if key in EXEMPT_KEYS:
                continue
            tag = '対象外' if key in SKIP_KEYS else '要修正'
            if key in SKIP_KEYS:
                skip += 1
            else:
                ng += 1
            print(f'  [{tag}] {rel} L{i} {key} … {"／".join(h)}')
            print(f'          {lit[:70]}')
    print(f'\n■ 要修正 {ng}件 ／ 対象外（設問部・軸ラベル） {skip}件')
    print('  対象外はサイトで直さない。投稿側の持ち場なので weekly に報告する')
    print('  古い週を直すかどうかは reference/todo.md「【決着】結果画面の「残る／残す」」が正典')
    return 0


if __name__ == '__main__':
    sys.exit(main())
