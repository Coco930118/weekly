from PIL import Image, ImageDraw, ImageFont
import os
SHINDAN=os.environ.get('SHINDAN_DIR','.')
def _p(r): return os.path.join(SHINDAN,r)
SH='ShipporiB1-700.ttf'; NS='NotoSansJP-400.ttf'; NB='NotoSansJP-700.ttf'
W,H=1280,670
BG={'kankei':(251,248,241),'soshiki':(241,236,225)}
INK=(43,38,32); BROWN=(150,106,62); SUB=(126,118,106); RULE=(196,184,164)
CH={'shiratama':('しらたま','shiratama-fig.png'),'shizuku':('しずく','shizuku-fig.png'),
    'hiyori':('ひより','hiyori-fig.png')}
def _logo():
    s=Image.open(_p('og/kankei-08-31.png')).convert('RGB').crop((1050,489,1161,595))
    m=Image.new('L',s.size,0); ImageDraw.Draw(m).ellipse((2,2,s.size[0]-3,s.size[1]-3),fill=255)
    return s,m
def build(dom,typename,stage,to_lines,out):
    ch,fig=CH[stage]
    bg=BG[dom]; im=Image.new('RGBA',(W,H),bg+(255,)); d=ImageDraw.Draw(im)
    d.rectangle((29,29,W-30,H-29),outline=(214,201,178),width=2)
    d.text((92,66),'Coco Methodology ── 間合い診断',font=ImageFont.truetype(NB,22),fill=BROWN,anchor='la')
    d.text((92,116),'この回は、',font=ImageFont.truetype(NS,25),fill=SUB,anchor='la')
    size=56
    while size>40:
        f=ImageFont.truetype(SH,size)
        if max(f.getbbox(l)[2] for l in to_lines)+92<=880: break
        size-=2
    f=ImageFont.truetype(SH,size); pitch=int(size*1.5)
    for i,l in enumerate(to_lines): d.text((90,156+i*pitch),l,font=f,fill=INK,anchor='la')
    y=156+len(to_lines)*pitch+8
    d.text((92,y),f'この間合いを〈{typename}〉と呼びます。付き添うのは {ch}。',
           font=ImageFont.truetype(NS,24),fill=SUB,anchor='la')
    # ── 無料で今できること（新規にとって唯一の行動） ──
    by=y+66
    d.rectangle((88,by,1192,by+112),outline=RULE,width=2)
    d.text((116,by+22),'人との距離のとり方には、型がある。',font=ImageFont.truetype(NB,30),fill=INK,anchor='la')
    d.text((116,by+66),'8問 / 約1分で、あなたの型に名前がつく。',font=ImageFont.truetype(NB,27),fill=BROWN,anchor='la')
    d.text((92,H-96),'ちがう型の回も、読んでみて。自分の回は自分のために、ちがう回は相手を読むために。',
           font=ImageFont.truetype(NS,22),fill=SUB,anchor='la')
    d.text((92,H-60),'この案内は毎回同じ。記事は、この下から。',font=ImageFont.truetype(NS,20),fill=SUB,anchor='la')
    a=Image.open(_p(f'assets/char/{fig}')).convert('RGBA'); a.thumbnail((215,215))
    im.alpha_composite(a,(W-100-a.width,132))
    s,m=_logo(); im.paste(s,(W-146,H-152),m)
    im.convert('RGB').save(out)
