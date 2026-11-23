"""Yazı tiplerini uygulamanın kullandığı karakter, ağırlık ve genişliklere indirger (web/fonts/*.woff2).

Kaynak: github.com/google/fonts (ofl/newsreader, ofl/ibmplexsans) değişken TTF dosyaları.
Kullanım:  pip install fonttools brotli
           python tools/yazitipi_altkume.py <kaynak-klasör> web/fonts
Karakter ya da ağırlık eklenirse web/fontlar.css içindeki font-weight/font-stretch aralıkları da güncellenmeli.
"""
import sys, os
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools import subset

kaynak, cikti = sys.argv[1], sys.argv[2]
UNICODES = ("U+0020-007E,U+00A0-00FF,U+011E-011F,U+0130-0131,U+015E-015F,U+0152-0153,U+02C6,U+02DA,U+02DC,"
            "U+2010-2027,U+2030-203A,U+2044,U+20AC,U+20BA,U+2122,U+2190-2199,U+2212")
OZELLIK = "kern,liga,calt,ccmp,locl,mark,mkmk,tnum,lnum,pnum,case"
ISLER = [
    # (kaynak dosya, çıktı adı, eksen sınırları)
    ("Newsreader[opsz,wght].ttf", "newsreader-normal.woff2", {"wght": (400, 600)}),
    ("Newsreader-Italic[opsz,wght].ttf", "newsreader-italic.woff2", {"wght": 400, "opsz": 16}),
    ("IBMPlexSans[wdth,wght].ttf", "ibm-plex-sans-normal.woff2", {"wght": (400, 700), "wdth": (92, 100)}),
    ("IBMPlexSans-Italic[wdth,wght].ttf", "ibm-plex-sans-italic.woff2", {"wght": (400, 600), "wdth": (100, 100)}),
]
mod = sys.argv[3] if len(sys.argv) > 3 else ""
for src, out, eksen in ISLER:
    f = TTFont(os.path.join(kaynak, src), lazy=False)
    if "opsz" in [a.axisTag for a in f["fvar"].axes] and "opsz" not in eksen:
        eksen = {**eksen, "opsz": (12, 48)}
    opt = subset.Options(); opt.layout_features = OZELLIK.split(","); opt.name_IDs = ["*"]
    opt.notdef_outline = True; opt.hinting = False
    s = subset.Subsetter(opt); s.populate(unicodes=subset.parse_unicodes(UNICODES)); s.subset(f)
    f = instancer.instantiateVariableFont(f, eksen, updateFontNames=False)
    yol = os.path.join(cikti, out); f.flavor = "woff2"; f.save(yol)
    print(f"{out:32} {os.path.getsize(yol) / 1024:6.1f} KB  eksenler: {[(a.axisTag, a.minValue, a.maxValue) for a in f['fvar'].axes] if 'fvar' in f else 'sabit'}")
