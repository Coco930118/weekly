#!/usr/bin/env python3
"""noteの型マガジン表紙（1280x670）。正典は rules/image.md／マガジン名は rules/note.md。
結果シェアOG（tools/ogshare.py）とは別物：あちらは診断へ誘う絵、こちらは有料マガジンの表紙。
診断のCTA（あなたは？ 8問）は入れない。"""
from PIL import Image, ImageDraw, ImageFont
import os
SHINDAN=os.environ.get('SHINDAN_DIR','.')
def _p(r): return os.path.join(SHINDAN,r)
SH='ShipporiB1-700.ttf'; NS='NotoSansJP-400.ttf'; NB='NotoSansJP-700.ttf'
W,H=1280,670
BG={'kankei':(251,248,241),'soshiki':(241,236,225)}
PLAN={'kankei':'💗 距離の整え方 —— 恋愛と関係','soshiki':'💼 温度の整え方 —— 組織と仕事'}
PLANTXT={'kankei':'距離の整え方 —— 恋愛と関係','soshiki':'温度の整え方 —— 組織と仕事'}
MARK={'kankei':'shiratama','soshiki':'shiratama'}
INK=(43,38,32); BROWN=(150,106,62); SUB=(126,118,106); RULE=(196,184,164)
def _logo():
    src=Image.open(_p('og/kankei-08-31.png')).convert('RGB').crop((1050,489,1161,595))
    m=Image.new('L',src.size,0); ImageDraw.Draw(m).ellipse((2,2,src.size[0]-3,src.size[1]-3),fill=255)
    return src,m
def wrap(tag):
    p=[x for x in tag.replace('。','。\n').split('\n') if x]
    if len(p)<=2: return (p+[''])[:2]
    return [''.join(p[:len(p)//2]), ''.join(p[len(p)//2:])]
def build(dom,typename,tag,char,out):
    bg=BG[dom]; im=Image.new('RGBA',(W,H),bg+(255,)); d=ImageDraw.Draw(im)
    d.rectangle((29,29,W-30,H-29),outline=(214,201,178),width=2)
    d.text((92,96),PLANTXT[dom],font=ImageFont.truetype(NB,24),fill=BROWN,anchor='la')
    d.line((92,148,150,148),fill=BROWN,width=2)
    name=typename+'へ'
    d.text((86,196),name,font=ImageFont.truetype(SH,126 if len(name)<=5 else 112),fill=INK,anchor='la')
    l1,l2=wrap(tag); tf=ImageFont.truetype(NS,30)
    d.text((92,404),l1,font=tf,fill=INK,anchor='la')
    if l2: d.text((92,450),l2,font=tf,fill=INK,anchor='la')
    d.line((92,528,600,528),fill=RULE,width=2)
    d.text((92,552),'Coco Methodology ── 間合いの型',font=ImageFont.truetype(NS,24),fill=SUB,anchor='la')
    a=Image.open(_p(f'assets/char/{char}')).convert('RGBA'); a.thumbnail((380,380))
    im.alpha_composite(a,(W-70-a.width,320-a.height//2+60))
    s,m=_logo(); im.paste(s,(W-150,H-160),m)
    im.convert('RGB').save(out)
