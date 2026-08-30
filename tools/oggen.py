#!/usr/bin/env python3
"""間合い診断の日別OG（1200x630）を生成する。

既存OGをテンプレートにして、見出しの矩形だけを地色で塗りつぶして描き直す。
枠線・アイブロウ・動物3匹・ロゴ・下部の一行は原本のまま残るので、体裁が完全に一致する。
（生成元の oggen.html は shindan 側で .gitignore されていて存在しないため、weekly 側に置く）

■ フォントの取り方（重要）
  CDN（jsdelivr / unpkg）は塞がれている。gstatic のURL直書きも版が上がると404になる。
  fonts.googleapis.com の CSS API に聞いて、返ってきた実URLを叩く2段にする:

    U=$(curl -sSL "https://fonts.googleapis.com/css2?family=Shippori+Mincho+B1:wght@700" \
        | grep -o 'https://fonts.gstatic.com[^)]*' | head -1)
    curl -sSL -o ShipporiB1-700.ttf "$U"

■ 使い方
    python3 tools/oggen.py <テンプレPNG> <出力PNG> <1行目> <2行目>
  例) python3 tools/oggen.py og/kankei-08-31.png og/kankei-09-01.png "誘うのはいつも、" "こちらからだった"

■ 実測で合わせた値（原本との平均画素差 1.06＝アンチエイリアスのみ）
  Shippori Mincho B1 / weight700 / 60px / 墨色(43,38,32) / 原点x85 / 1行目y192 / 行送り82
  1行は 660px まで（動物の帯が690pxから始まる）＝全角9字が目安
"""
import sys, re
from PIL import Image, ImageDraw, ImageFont

FONT   = 'ShipporiB1-700.ttf'   # Shippori Mincho B1 Bold
SIZE   = 60
INK    = (43, 38, 32)
X      = 85                   # 描画原点（実測の左端87に合う）
Y1, PITCH = 192, 82           # 1行目の描画y、行送り
CLEAR  = (80, 200, 690, 356)  # 見出しだけを消す矩形

def render(template, out, line1, line2):
    im = Image.open(template).convert('RGBA')
    bg = im.convert('RGB').getpixel((600, 600))
    ImageDraw.Draw(im).rectangle(CLEAR, fill=bg + (255,))
    d = ImageDraw.Draw(im); f = ImageFont.truetype(FONT, SIZE)
    for i, t in enumerate([line1, line2]):
        if t: d.text((X, Y1 + i * PITCH), t, font=f, fill=INK, anchor='la')
    im.save(out)

if __name__ == '__main__':
    tpl, out, l1, l2 = sys.argv[1:5]
    render(tpl, out, l1, l2)
