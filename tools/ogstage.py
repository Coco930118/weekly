#!/usr/bin/env python3
"""noteの本文に差し込む「型 × 段」の画像（1280x670）。8型 × 3段 ＝ 24枚。
3匹は型ではなく段につく（weekly rules/type.md「3匹は『型』ではなく『声』に当てる」）。
段の定義は既存note『Coco Methodologyとは？』の表から逐語。新規に作らない。"""
from PIL import Image, ImageDraw, ImageFont
import os
SHINDAN=os.environ.get('SHINDAN_DIR','.')
def _p(r): return os.path.join(SHINDAN,r)
SH='ShipporiB1-700.ttf'; NS='NotoSansJP-400.ttf'; NB='NotoSansJP-700.ttf'
W,H=1280,670
BG={'kankei':(251,248,241),'soshiki':(241,236,225)}
PLAN={'kankei':'距離の整え方 —— 恋愛と関係','soshiki':'温度の整え方 —— 組織と仕事'}
INK=(43,38,32); BROWN=(150,106,62); SUB=(126,118,106); RULE=(196,184,164)
STAGE={
 'shiratama':('受け止める','しらたま','起きていることに、名前をつける','名前がつく','shiratama-fig.png'),
 'shizuku':  ('整える',    'しずく',  '混ざっているものを、分ける',      '分かれる',  'shizuku-fig.png'),
 'hiyori':   ('動く',      'ひより',  '今日決められることを、一つ出す',  '一つ決まる','hiyori-fig.png'),
}
def _logo():
    src=Image.open(_p('og/kankei-08-31.png')).convert('RGB').crop((1050,489,1161,595))
    m=Image.new('L',src.size,0); ImageDraw.Draw(m).ellipse((2,2,src.size[0]-3,src.size[1]-3),fill=255)
    return src,m
def build(dom,typename,stage,out):
    st,chname,does,gets,fig=STAGE[stage]
    bg=BG[dom]; im=Image.new('RGBA',(W,H),bg+(255,)); d=ImageDraw.Draw(im)
    d.rectangle((29,29,W-30,H-29),outline=(214,201,178),width=2)
    d.text((92,92),PLAN[dom],font=ImageFont.truetype(NB,23),fill=BROWN,anchor='la')
    d.line((92,142,150,142),fill=BROWN,width=2)
    head=typename+'の回'
    d.text((86,182),head,font=ImageFont.truetype(SH,104 if len(head)<=6 else 92),fill=INK,anchor='la')
    d.line((92,342,700,342),fill=RULE,width=2)
    d.text((92,376),f'三段のうち　{st}',font=ImageFont.truetype(NB,44),fill=INK,anchor='la')
    d.text((92,452),does+'。',font=ImageFont.truetype(NS,29),fill=INK,anchor='la')
    d.text((92,502),f'この回で出てくるもの ── {gets}',font=ImageFont.truetype(NS,25),fill=SUB,anchor='la')
    d.text((92,556),f'声は {chname}',font=ImageFont.truetype(NS,24),fill=BROWN,anchor='la')
    a=Image.open(_p(f'assets/char/{fig}')).convert('RGBA'); a.thumbnail((360,360))
    im.alpha_composite(a,(W-80-a.width,300-a.height//2+50))
    s,m=_logo(); im.paste(s,(W-150,H-160),m)
    im.convert('RGB').save(out)
