#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""間合いの型（8型＋中央）を、正典 rules/type.md から読む共通モジュール。

【なぜ正典から読むか】型名をツールに手で持たせると、正典を直したときに検査が
追随しない。2026-08-31 の恒久ルール整合チェックで、この形の事故を6件処理した
ばかりで、そのうち3件は「毎回読む／最上位を名乗るファイルが古い条文を持って
いた」というものだった。ツールで同じ形を新しく作らない。

e373.py が素材台帳（reference/episodes_soshiki.json の E373）から読むのと
同じ方針。**型の正典は rules/type.md の「軸と10型」の表だけ。**

読むのは表の1列目（軸）・2列目（恋愛の型）・4列目（組織の型）。
中央「保つ人」は返さない——処方を渡せない型なので、週次の宛先にならない
（rules/check.md ⑤／rules/note.md「中央『保つ人』は割り当てない」）。
"""
import os
import re

TYPE_MD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'rules', 'type.md')


def _rows(path):
    """「軸と10型」の表の行を、セルのリストとして順に返す"""
    try:
        text = open(path, encoding='utf-8').read()
    except OSError:
        return
    # 見出し「## 軸と10型」から次の見出しまでを切り出す（他の表を拾わないため）
    m = re.search(r'^##\s*軸と10型.*?$(.*?)(?=^##\s|\Z)', text, re.M | re.S)
    if not m:
        return
    for line in m.group(1).split('\n'):
        line = line.strip()
        if not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) >= 5:
            yield cells


def _name(cell):
    """セルから型名を取り出す（**溶ける人** → 溶ける人）"""
    m = re.search(r'\*\*(.+?)\*\*', cell)
    return (m.group(1) if m else cell).strip()


def types(path=TYPE_MD):
    """{'恋愛': [4型], '組織': [4型]} を返す。中央は含めない。
    読めなければ空リスト（検査そのものは止めない）"""
    out = {'恋愛': [], '組織': []}
    for cells in _rows(path):
        axis = cells[0]
        if not axis.startswith('温度'):      # 見出し行・区切り行・中央行を落とす
            continue
        love, org = _name(cells[1]), _name(cells[3])
        if love and love not in out['恋愛']:
            out['恋愛'].append(love)
        if org and org not in out['組織']:
            out['組織'].append(org)
    return out


def center(path=TYPE_MD):
    """中央の型名を返す（割り当て禁止の対象を名指しするため）"""
    for cells in _rows(path):
        if cells[0].startswith('中央'):
            return _name(cells[1])
    return '保つ人'


if __name__ == '__main__':
    t = types()
    print('恋愛（Threads の宛先）:', ' / '.join(t['恋愛']) or '(読めなかった)')
    print('組織（X の宛先）      :', ' / '.join(t['組織']) or '(読めなかった)')
    print('中央（割り当てない）  :', center())
