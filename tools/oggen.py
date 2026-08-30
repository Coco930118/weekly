#!/usr/bin/env python3
"""間合い診断の日別OG（1200x630）を組む。正典は rules/image.md「間合い診断のOG画像」。

■ フォントの取り方（CDNは塞がれている・URL直書きは版が上がって404になる）
    U=$(curl -sSL "https://fonts.googleapis.com/css2?family=Shippori+Mincho+B1:wght@700" \
        | grep -o 'https://fonts.gstatic.com[^)]*' | head -1)
    curl -sSL -o ShipporiB1-700.ttf "$U"
  同じ手順で Noto+Sans+JP の 400 と 700 も取る。

■ 使い方
    from oggen import build
    build('kankei', 'og/kankei-09-01.png', '誘うのはいつも、', 'こちらからだった')

■ 素材
  3匹  /home/user/shindan/assets/char/{shizuku,shiratama,hiyori}-fig.png
  ロゴ  既存OG（og/kankei-08-31.png）の右下から円形マスクで切り出して再利用

■ 実測で確定した値（見出しは原本との平均画素差 1.06＝アンチエイリアスのみ）
  見出し  Shippori Mincho B1 / 700 / 54px（長い回は38pxまで自動縮小） / 墨(43,38,32) / x85 / y200 / 行送り80 / 1行は全角9字まで
  型名    Noto Sans JP 700 / 40px / 2列（x690・x950）× 2行（y218・y300）
  地色    kankei (251,248,241) ／ soshiki (241,236,225)
"""
from PIL import Image, ImageDraw, ImageFont
SH='ShipporiB1-700.ttf'; NS='NotoSansJP-400.ttf'; NB='NotoSansJP-700.ttf'
BG={'kankei':(251,248,241),'soshiki':(241,236,225)}
EYE={'kankei':'恋愛と関係','soshiki':'組織と仕事'}
INK=(43,38,32); BROWN=(150,106,62); SUB=(126,118,106); RULE=(196,184,164)
T={'kankei':['溶ける人','秘める人','尽くす人','守る人'],
   'soshiki':['背負う人','こらえる人','先に動く人','降りる人']}
LOGO=None
def logo():
    global LOGO
    if LOGO is None:
        src=Image.open('/home/user/shindan/og/kankei-08-31.png').convert('RGB').crop((1050,489,1161,595))
        m=Image.new('L',src.size,0); dm=ImageDraw.Draw(m); dm.ellipse((2,2,src.size[0]-3,src.size[1]-3),fill=255)
        LOGO=(src,m)
    return LOGO

def build(dom,out,l1,l2):
    bg=BG[dom]; im=Image.new('RGBA',(1200,630),bg+(255,)); d=ImageDraw.Draw(im)
    d.rectangle((27,27,1172,602),outline=(214,201,178),width=2)          # 枠
    # アイブロウ
    d.text((85,110),f'{EYE[dom]}　──　間合い診断',font=ImageFont.truetype(NB,23),fill=BROWN,anchor='la')
    d.line((85,158,138,158),fill=BROWN,width=2)
    # 見出し
    # 見出しは自動縮小。型名の帯（x690〜）に食い込ませない
    size=54
    while size>38:
        hf=ImageFont.truetype(SH,size)
        if 85+max(hf.getbbox(l1)[2],hf.getbbox(l2)[2])<=660: break
        size-=2
    hf=ImageFont.truetype(SH,size); pitch=int(size*1.48)
    top=200+(54-size)//2
    d.text((85,top),l1,font=hf,fill=INK,anchor='la')
    d.text((85,top+pitch),l2,font=hf,fill=INK,anchor='la')
    # 3匹（大きく・下段左）
    for i,n in enumerate(['shizuku','shiratama','hiyori']):
        a=Image.open(f'/home/user/shindan/assets/char/{n}-fig.png').convert('RGBA')
        a.thumbnail((200,200)); im.alpha_composite(a,(70+i*192,370))
    # 型名 2×2（右・大きく）
    tf=ImageFont.truetype(NB,40); names=T[dom]
    cols=[690,950]; rows=[218,300]
    for i,nm in enumerate(names):
        d.text((cols[i%2],rows[i//2]),nm,font=tf,fill=INK,anchor='la')
    d.line((690,392,1152,392),fill=RULE,width=2)
    d.text((690,422),'あなたは、どれ？',font=ImageFont.truetype(NB,38),fill=BROWN,anchor='la')
    d.text((690,486),'8問 / 約1分で、名前がつく。',font=ImageFont.truetype(NS,25),fill=SUB,anchor='la')
    src,m=logo(); im.paste(src,(1050,489),m)
    im.convert('RGB').save(out)
