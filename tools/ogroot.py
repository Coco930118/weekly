from PIL import Image, ImageDraw, ImageFont
import os
SHINDAN=os.environ.get('SHINDAN_DIR','.')
def _p(r): return os.path.join(SHINDAN,r)
SH='ShipporiB1-700.ttf'; NS='NotoSansJP-400.ttf'; NB='NotoSansJP-700.ttf'
PAPER=(251,248,241); INK=(43,38,32); BROWN=(150,106,62); SUB=(126,118,106); RULE=(196,184,164)
K=['溶ける人','秘める人','尽くす人','守る人']; S=['背負う人','こらえる人','先に動く人','降りる人']
def _logo():
    src=Image.open(_p('og/kankei-08-31.png')).convert('RGB').crop((1050,489,1161,595))
    m=Image.new('L',src.size,0); ImageDraw.Draw(m).ellipse((2,2,src.size[0]-3,src.size[1]-3),fill=255)
    return src,m
def _row(d,y,label,names,lf,tf):
    """ラベル＋型名を1行に組んで中央寄せ。"""
    sep='／'; body=sep.join(names)
    wl=lf.getbbox(label)[2]; gap=26; wb=tf.getbbox(body)[2]
    x=(1200-(wl+gap+wb))//2
    d.text((x,y+7),label,font=lf,fill=BROWN,anchor='la')
    d.text((x+wl+gap,y),body,font=tf,fill=INK,anchor='la')

def build_root(out):
    im=Image.new('RGBA',(1200,630),PAPER+(255,)); d=ImageDraw.Draw(im)
    d.rectangle((27,27,1172,602),outline=(214,201,178),width=2)
    d.text((600,84),'The Art of Temperature & Distance',
           font=ImageFont.truetype(NS,22),fill=BROWN,anchor='ma')
    hf=ImageFont.truetype(SH,62)
    d.text((600,126),'あなたの間合いには、',font=hf,fill=INK,anchor='ma')
    d.text((600,198),'型がある。',font=hf,fill=INK,anchor='ma')
    lf=ImageFont.truetype(NS,21); tf=ImageFont.truetype(NB,29)
    _row(d,300,'恋愛に4つ',K,lf,tf)
    _row(d,352,'仕事に4つ',S,lf,tf)
    for i,n in enumerate(['shizuku','shiratama','hiyori']):
        a=Image.open(_p(f'assets/char/{n}-fig.png')).convert('RGBA'); a.thumbnail((122,122))
        im.alpha_composite(a,(482+i*118,432))
    d.text((600,562),'8問 / 約1分で、あなたの型に名前がつく。',
           font=ImageFont.truetype(NS,24),fill=SUB,anchor='ma')
    s,m=_logo(); im.paste(s,(1046,468),m)
    im.convert('RGB').save(out)
