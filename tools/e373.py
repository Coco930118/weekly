#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E373（Cocoの休日と好きなもの）の素材を、台帳から読む共通モジュール。

【なぜ台帳から読むか】WIT_HINTS を各ツールに手で持たせると、素材を足したときに
検出が追随しない。2026-08-29 のWチェックで、この形の事故が実際に3件出た：
  ・E373 に「ベランダ・昼寝」を足しても、検出語は増えなかった
  ・逆に E373 に無い「湯船」を、ツールが今もウィットとして検出していた
    （2026-08-27 に「湯船は E373 にない」として直した違反を、ツールが推奨し返す状態）
  ・機械3本・目視3本なのに、中身が3本とも入れ替わっていた（9/1週35投稿）

素材の正典は reference/episodes_soshiki.json の E373 だけにする。
要素を足すときは台帳の key_phrases と elements を直す。ツールは触らない。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPISODES = os.path.join(ROOT, 'reference', 'episodes_soshiki.json')


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def elements(path=EPISODES):
    """E373 の elements を返す。読めなければ空リスト（検査そのものは止めない）"""
    try:
        d = json.load(open(path, encoding='utf-8'))
    except (OSError, ValueError):
        return []
    for o in _walk(d):
        if isinstance(o, dict) and o.get('id') == 'E373':
            return list(o.get('elements', []))
    return []


def count_in(text, els=None):
    """text に出てくる E373 要素を返す（重複なし）"""
    els = elements() if els is None else els
    return [e for e in els if e in text]
