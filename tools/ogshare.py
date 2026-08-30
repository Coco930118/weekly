#!/usr/bin/env python3
"""間合い診断の【結果シェア】OG（1200x630・型別10枚）を組む。
正典は rules/image.md「間合い診断のOG画像」。入口用は tools/oggen.py（別物・混ぜない）。

    from ogshare import build
    build('kankei','溶ける人','好きになった相手には、…型。',['shiratama-fig.png'],'og/share-kankei-HH.png')

フォントの取り方は tools/oggen.py の docstring と同じ（CDNは塞がれている）。
型名・一行タグ・代表キャラは shindan の data-w*.js と assets/shindan.js から引く。
言葉の正典は weekly の rules/type.md。
"""
from PIL import Image, ImageDraw, ImageFont
SH='ShipporiB1-700.ttf'; NS='NotoSansJP-400.ttf'; NB='NotoSansJP-700.ttf'
BG={'kankei':(251,248,241),'soshiki':(241,236,225)}
EYE={'kankei':'恋愛と関係','soshiki':'組織と仕事'}
INK=(43,38,32); BROWN=(150,106,62); SUB=(126,118,106); RULE=(196,184,164)
import os
SHINDAN=os.environ.get('SHINDAN_DIR','.')
def _p(rel): return os.path.join(SHINDAN,rel)
CH=_p('assets/char')+'/'
def _logo():
    src=Image.open(_p('og/kankei-08-31.png')).convert('RGB').crop((1050,489,1161,595))
    m=Image.new('L',src.size,0); ImageDraw.Draw(m).ellipse((2,2,src.size[0]-3,src.size[1]-3),fill=255)
    return src,m
def wrap(tag):
    p=[x for x in tag.replace('。','。\n').split('\n') if x]
    if len(p)<=2: return (p+[''])[:2]
    return [''.join(p[:len(p)//2]), ''.join(p[len(p)//2:])]
def build(dom,typename,tag,chars,out):
    bg=BG[dom]; im=Image.new('RGBA',(1200,630),bg+(255,)); d=ImageDraw.Draw(im)
    d.rectangle((27,27,1172,602),outline=(214,201,178),width=2)
    d.text((85,96),f'{EYE[dom]}　──　間合い診断',font=ImageFont.truetype(NB,23),fill=BROWN,anchor='la')
    d.line((85,142,138,142),fill=BROWN,width=2)
    d.text((85,182),'わたしは',font=ImageFont.truetype(NS,30),fill=SUB,anchor='la')
    d.text((80,222),typename,font=ImageFont.truetype(SH,118 if len(typename)<=4 else 104),fill=INK,anchor='la')
    l1,l2=wrap(tag); tf=ImageFont.truetype(NS,29)
    d.text((85,396),l1,font=tf,fill=INK,anchor='la')
    if l2: d.text((85,440),l2,font=tf,fill=INK,anchor='la')
    d.line((85,500,560,500),fill=RULE,width=2)
    d.text((85,524),'あなたは？',font=ImageFont.truetype(NB,32),fill=BROWN,anchor='la')
    d.text((262,532),'8問 / 約1分',font=ImageFont.truetype(NS,25),fill=SUB,anchor='la')
    if len(chars)==1:
        a=Image.open(CH+chars[0]).convert('RGBA'); a.thumbnail((360,360))
        im.alpha_composite(a,(1150-a.width,300-a.height//2+40))
    else:
        for i,c in enumerate(chars):
            a=Image.open(CH+c).convert('RGBA'); a.thumbnail((208,208))
            im.alpha_composite(a,(690+i*158,236))
    s,m=_logo(); im.paste(s,(1050,489),m)
    im.convert('RGB').save(out)
