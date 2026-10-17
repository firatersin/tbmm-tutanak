"""Sayfa iskeleti ve ortak bileşenler: HTML çerçevesi, içerik güvenliği politikası, alt sekmeler, oy sayımı,
parti renk kareleri, kaynak (provenance) alt bilgisi."""
from __future__ import annotations

import base64
import colorsys
import hashlib
import json
import re
from html import escape

PROJE_ID = "meclis-ce5d2"
REPO = "https://github.com/firatersin/tbmm-tutanak"

FIREBASE_KAYNAK = {
    "script": "https://www.gstatic.com/firebasejs/ https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/",
    "connect": ("https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://firestore.googleapis.com "
                "https://content-firebaseappcheck.googleapis.com https://www.google.com/recaptcha/"),
    "frame": f"https://www.google.com/recaptcha/ https://recaptcha.google.com/recaptcha/ https://{PROJE_ID}.firebaseapp.com",
}

# Temayı ilk boyamadan önce uygula (yanıp sönmeyi önler). İçerik politikası bu betiğin özetine izin verir.
TEMA_JS = ("try{var t=localStorage.getItem('tbmm-tema');if(t)document.documentElement.dataset.tema=t;"
           "var b=localStorage.getItem('tbmm-boyut');if(b)document.documentElement.style.setProperty('--okuma',b+'px')}catch(e){}")


def csp(html: str, firebase: bool) -> str:
    """Sayfadaki satır içi betiklerin SHA-256 özetleriyle İçerik Güvenliği Politikası; başka betik çalışmaz."""
    ozetler = " ".join(
        "'sha256-" + base64.b64encode(hashlib.sha256(s.encode("utf-8")).digest()).decode() + "'"
        for s in re.findall(r"<script(?: type=\"module\")?>(.*?)</script>", html, re.S))
    dis = FIREBASE_KAYNAK if firebase else {"script": "", "connect": "", "frame": ""}
    kurallar = [
        "default-src 'self'",
        f"script-src 'self' {ozetler} {dis['script']}".strip(),
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self'",
        "img-src 'self' data:",
        f"connect-src 'self' {dis['connect']}".strip(),
        f"frame-src {dis['frame'] or chr(39) + 'none' + chr(39)}",
        "worker-src 'self'", "manifest-src 'self'",
        "object-src 'none'", "base-uri 'none'", "form-action 'self'",
    ]
    return f'<meta http-equiv="Content-Security-Policy" content="{"; ".join(kurallar)}">'


# ---------- Simgeler (24×24, tek çizgi kalınlığı) ----------

def _svg(yol: str) -> str:
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{yol}</svg>')


SIMGE = {
    # metin sütunu
    "akis": _svg('<path d="M4 6h16M4 10h16M4 14h16M4 18h10"/>'),
    # Genel Kurul yarım dairesi
    "oturumlar": _svg('<path d="M2.5 18.5h19"/><path d="M4.5 18.5a7.5 7.5 0 0 1 15 0"/><path d="M8.5 18.5a3.5 3.5 0 0 1 7 0"/>'
                      '<circle cx="12" cy="7.2" r=".6" fill="currentColor"/>'),
    # sayım çizgileri
    "oylamalar": _svg('<path d="M6 5v14M10 5v14M14 5v14M18 5v14M3.5 16 20.5 8"/>'),
    "ara": _svg('<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>'),
    "takip": _svg('<path d="M6.5 3.5h11v17l-5.5-3.8-5.5 3.8z"/>'),
}

SEKMELER = [("akis", "Akış", "index.html"), ("oturumlar", "Oturumlar", "oturumlar.html"),
            ("oylamalar", "Oylamalar", "oylamalar.html"), ("ara", "Ara", "ara.html"), ("takip", "Takip", "takip.html")]


def alt_nav(aktif: str | None) -> str:
    ogeler = "".join(
        f'<li><a href="{url}"{" aria-current=\"page\"" if anahtar == aktif else ""}>{SIMGE[anahtar]}{ad}</a></li>'
        for anahtar, ad, url in SEKMELER)
    return f'<nav class="alt-nav" aria-label="Ana gezinme"><ul>{ogeler}</ul></nav>'


def ust_bant(geri: tuple[str, str] | None = None, sag: str = "") -> str:
    sol = (f'<a class="geri" href="{escape(geri[1])}">← {escape(geri[0])}</a>' if geri
           else '<a class="imza" href="index.html">Meclis <span>Tutanakları</span></a>')
    return f'<header class="ust"><div class="kap">{sol}<div class="sag">{sag}</div></div></header>'


def sayfa(baslik: str, govde: str, *, sekme: str | None = None, geri: tuple[str, str] | None = None,
          modul: str | None = None, firebase: bool = False, aciklama: str = "", ust_sag: str = "",
          nav: bool = True) -> str:
    modul_html = f'<script type="module" src="js/{modul}"></script>' if modul else ""
    html = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="referrer" content="strict-origin-when-cross-origin">
__CSP__<title>{escape(baslik)}</title>
{f'<meta name="description" content="{escape(aciklama)}">' if aciklama else ''}
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#F7F2E8" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1A1714" media="(prefers-color-scheme: dark)">
<link rel="icon" href="favicon-32.png" sizes="32x32"><link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Meclis"><meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="preload" href="fonts/newsreader-normal-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="fonts/ibm-plex-sans-normal-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="fontlar.css"><link rel="stylesheet" href="stil.css"><link rel="stylesheet" href="partiler.css">
<script>{TEMA_JS}</script>
</head><body>
<a class="gizli-metin" href="#ana">İçeriğe geç</a>
{ust_bant(geri, ust_sag)}
<main id="ana">{govde}</main>
{alt_nav(sekme) if nav else ''}
<script type="module" src="js/ortak.js"></script>{modul_html}
</body></html>"""
    return html.replace("__CSP__", csp(html, firebase), 1)


def veri_blogu(kimlik: str, veri) -> str:
    """Sayfa betiklerine veri: çalıştırılmayan JSON bloğu (içerik politikası gerektirmez)."""
    metin = json.dumps(veri, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/json" id="{kimlik}">{metin}</script>'


# ---------- Oy sayımı ----------

OY_TURLERI = [("KABUL", "Kabul", "k", "✓"), ("RET", "Ret", "r", "✕"),
              ("ÇEKİMSER", "Çekimser", "c", "–"), ("KATILMADI", "Katılmadı", "x", "·")]


def sayim(sayilar: dict | list, *, sinif: str = "", etiket: bool = True, toplam_metin: bool = False) -> str:
    """Tek çubukluk oy sayımı: 2 px aralıklı dilimler, doğrudan etiketler (renk tek başına anlam taşımaz)."""
    if isinstance(sayilar, list):
        sayilar = dict(zip(["KABUL", "RET", "ÇEKİMSER", "KATILMADI"], sayilar))
    toplam = sum(sayilar.get(k, 0) for k, *_ in OY_TURLERI) or 1
    dilimler = "".join(
        f'<i class="{c}" style="flex:{sayilar[k]}" title="{ad}: {sayilar[k]}"></i>'
        for k, ad, c, _ in OY_TURLERI if sayilar.get(k))
    ozet = ", ".join(f"{ad} {sayilar.get(k, 0)}" for k, ad, _, _ in OY_TURLERI if sayilar.get(k))
    cubuk = f'<div class="sayim {sinif}" role="img" aria-label="{escape(ozet)}">{dilimler}</div>'
    if not etiket:
        return cubuk
    yazilar = "".join(
        f'<span><span class="isaret {c}" aria-hidden="true">{i}</span>{ad} <b>{sayilar.get(k, 0)}</b></span>'
        for k, ad, c, i in OY_TURLERI if sayilar.get(k) or k in ("KABUL", "RET"))
    return cubuk + f'<div class="sayilar" aria-hidden="true">{yazilar}</div>'


# ---------- Parti renk kareleri ----------

# Yaklaşık renkler; yalnızca ayırt etmeye yardım eder ve her zaman parti adıyla birlikte gösterilir.
PARTI_TABAN = {
    "AK Parti": "#F39200", "Yeni Parti": "#C8102E", "CHP": "#E30A17", "DEM Parti": "#7B2D8E", "MHP": "#A3161A",
    "İYİ Parti": "#1FA3DC", "Yeni Yol": "#1F5FA8", "YRP": "#2E7D5B", "HÜDA PAR": "#4C8C2B", "Saadet": "#B5123E",
    "TİP": "#D81F26", "EMEP": "#D9B600", "DBP": "#5E3A8C", "DSP": "#2D6DB5", "DP": "#6B7C8F",
    "Bağımsız": "#8A8578", "HDP": "#7B2D8E", "YSP": "#7B2D8E", "Gelecek": "#2A8C8C", "DEVA": "#1C7FB6",
}
# Aynı kırmızı aileden partiler (CHP, Yeni Parti) yalnızca renkle ayrılamaz: ikincisine tarama deseni
TARAMALI = {"Yeni Parti"}


def _parlaklik(hexr: str) -> float:
    r, g, b = (int(hexr[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _karsitlik(a: str, b: str) -> float:
    la, lb = sorted([_parlaklik(a), _parlaklik(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _ayarla(hexr: str, zemin: str, hedef: float = 3.0) -> str:
    """Rengin tonunu koruyup açıklığını, zemine karşı en az 3:1 karşıtlık (WCAG 1.4.11) sağlanana dek değiştirir."""
    r, g, b = (int(hexr[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    koyu_zemin = _parlaklik(zemin) < 0.2
    for _ in range(100):
        aday = "#%02x%02x%02x" % tuple(round(x * 255) for x in colorsys.hls_to_rgb(h, l, s))
        if _karsitlik(aday, zemin) >= hedef:
            return aday
        l = min(1, l + 0.01) if koyu_zemin else max(0, l - 0.01)
    return aday


def parti_sinif(parti: str) -> str:
    """CSS sınıf adı; Türkçe büyük İ/I önce doğru küçültülür ("İYİ Parti" → p-iyi-parti)."""
    kucuk = parti.replace("İ", "i").replace("I", "ı").lower()
    return "p-" + re.sub(r"[^a-z0-9]+", "-", kucuk.translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))).strip("-")


def parti_css(partiler: list[str]) -> str:
    """Her parti için açık ve koyu temada zemine karşı ≥3:1 karşıtlıklı kare rengi (yalnızca .sw karelerinde)."""
    acik, koyu_sistem, koyu_secili = [], [], []
    for p in partiler:
        taban, sinif = PARTI_TABAN.get(p, "#8A8578"), parti_sinif(p)
        a, k = _ayarla(taban, "#F7F2E8"), _ayarla(taban, "#1A1714")
        desen = (";background-image:repeating-linear-gradient(135deg,transparent 0 2px,var(--kagit) 2px 3.5px)"
                 if p in TARAMALI else "")
        acik.append(f".sw.{sinif}{{--p:{a}{desen}}}")
        koyu_sistem.append(f':root:not([data-tema="acik"]) .sw.{sinif}{{--p:{k}}}')
        koyu_secili.append(f':root[data-tema="koyu"] .sw.{sinif}{{--p:{k}}}')
    return ("/* Parti renkleri: yalnızca veri katmanı; zemine karşı ≥3:1 olacak şekilde ayarlanır. */\n"
            + "\n".join(acik)
            + "\n@media (prefers-color-scheme: dark){" + "".join(koyu_sistem) + "}\n"
            + "\n".join(koyu_secili) + "\n")


def parti_karesi(parti: str) -> str:
    return f'<i class="sw {parti_sinif(parti)}" aria-hidden="true"></i>'


# ---------- Kaynak alt bilgisi ----------

def kaynak_bilgisi(satirlar: list[str], tbmm_url: str = "", atif: str = "", ek_dugme: str = "") -> str:
    dugmeler = []
    if tbmm_url:
        dugmeler.append(f'<a href="{escape(tbmm_url)}" target="_blank" rel="noopener">TBMM\'deki kaynak ↗</a>')
    if atif:
        dugmeler.append(f'<button class="dugme yalin" data-kopyala="{escape(atif)}">Kaynak gösterimini kopyala</button>')
    if ek_dugme:
        dugmeler.append(ek_dugme)
    dugmeler.append(f'<a href="{REPO}/issues/new" target="_blank" rel="noopener">Hata bildir</a>')
    return (f'<footer class="kaynak">{"<br>".join(satirlar)}'
            f'<div class="dugmeler">{" ".join(dugmeler)}</div></footer>')
