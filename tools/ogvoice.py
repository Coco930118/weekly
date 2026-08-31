from PIL import Image, ImageDraw, ImageFont
import os
SHINDAN=os.environ.get('SHINDAN_DIR','.')
def _p(r): return os.path.join(SHINDAN,r)
SH='ShipporiB1-700.ttf'; NS='NotoSansJP-400.ttf'; NB='NotoSansJP-700.ttf'
W,H=1280,670
BG={'kankei':(251,248,241),'soshiki':(241,236,225)}
INK=(43,38,32); BROWN=(150,106,62); SUB=(126,118,106)
def _logo():
    s=Image.open(_p('og/kankei-08-31.png')).convert('RGB').crop((1050,489,1161,595))
    m=Image.new('L',s.size,0); ImageDraw.Draw(m).ellipse((2,2,s.size[0]-3,s.size[1]-3),fill=255)
    return s,m
def build(dom,ch,fig,lines,out):
    bg=BG[dom]; im=Image.new('RGBA',(W,H),bg+(255,)); d=ImageDraw.Draw(im)
    d.rectangle((29,29,W-30,H-29),outline=(214,201,178),width=2)
    a=Image.open(_p(f'assets/char/{fig}')).convert('RGBA'); a.thumbnail((300,300))
    im.alpha_composite(a,(96,(H-a.height)//2-30))
    x=440
    size=48
    while size>32:
        f=ImageFont.truetype(SH,size)
        if max(f.getbbox(l)[2] for l in lines)+x<=1180: break
        size-=2
    f=ImageFont.truetype(SH,size); pitch=int(size*1.72)
    top=(H-len(lines)*pitch)//2-40
    for i,l in enumerate(lines): d.text((x,top+i*pitch),l,font=f,fill=INK,anchor='la')
    d.text((x,top+len(lines)*pitch+14),f'── {ch}',font=ImageFont.truetype(NS,25),fill=SUB,anchor='la')
    d.text((x,H-124),'Coco Methodology ── 間合い診断',font=ImageFont.truetype(NB,22),fill=BROWN,anchor='la')
    d.text((x,H-84),'8問 / 約1分で、あなたの型に名前がつく。',font=ImageFont.truetype(NS,24),fill=SUB,anchor='la')
    s,m=_logo(); im.paste(s,(W-146,H-152),m)
    im.convert('RGB').save(out)
