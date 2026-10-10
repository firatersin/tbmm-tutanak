#!/usr/bin/env python3
"""data/ klasöründeki tutanak ve oylamalardan statik okuma sitesini üretir (site/ klasörü).

  python arayuz.py        # siteyi yeniden üret

tbmm_tutanak.py her çalıştığında bunu otomatik çağırır. Üretilen site sunucusuz çalışır:
yerelde site/index.html doğrudan açılabilir, GitHub Pages'te de aynen yayınlanır.
"""
from __future__ import annotations

import json
import re
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "site"
TR_TZ = timezone(timedelta(hours=3))

UPPER = "A-ZÇĞİÖŞÜÂÎÛ"
SPEAKER_RE = re.compile(rf"^([{UPPER}][{UPPER} .'’-]*?[{UPPER}])(?: \(([^)]*)\))?\s*[-–] (.*)$")
OTURUM_RE = re.compile(rf"^[{UPPER}]+ OTURUM$")
AGENDA_RE = re.compile(r"^(?:[IVXLC]+\.-|[A-ZÇĞİÖŞÜ]\)|\d+\.-)\s+\S")
NOISE_RE = re.compile(r"^(?:-+ ?\d+ ?-+|\d{1,2}/\d{1,2}/\d{4})$")
NOTE_RE = re.compile(r"\((?:[^()]*?(?:alkış|gürültü|sıralarından|Mikrofon|Hatip|kürsü|Gürültüler|ses)[^()]*)\)", re.I)
VERDICT_RE = re.compile(r"(kabul edil(?:di|medi)|reddedildi|ertelendi|geri çekildi|"
                        r"bilgiye sunuldu|seçildi|and içti)\.?$")

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
         "Eylül", "Ekim", "Kasım", "Aralık"]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

PARTI_KISA = {
    "Adalet ve Kalkınma Partisi": "AK Parti",
    "Cumhuriyet Halk Partisi": "CHP",
    "Milliyetçi Hareket Partisi": "MHP",
    "Halkların Eşitlik ve Demokrasi Partisi": "DEM Parti",
    "Halkların Demokratik Partisi": "HDP",
    "Yeşil Sol Parti": "YSP",
    "İYİ Parti": "İYİ Parti",
    "Yeni Yol Partisi": "Yeni Yol",
    "Yeni Parti": "Yeni Parti",
    "Yeniden Refah Partisi": "YRP",
    "Saadet Partisi": "Saadet",
    "Demokrat Parti": "DP",
    "Demokratik Bölgeler Partisi": "DBP",
    "Türkiye İşçi Partisi": "TİP",
    "Emek Partisi": "EMEP",
    "Demokrasi ve Atılım Partisi": "DEVA",
    "Gelecek Partisi": "Gelecek",
    "Hür Dava Partisi": "HÜDA PAR",
    "Demokratik Sol Parti": "DSP",
    "Bağımsız Milletvekili": "Bağımsız",
    "Bağımsız": "Bağımsız",
}
# Oy sütunları: (kod, etiket, css sınıfı)
OY_TURLERI = [("KABUL", "Kabul", "k"), ("RET", "Ret", "r"), ("ÇEKİMSER", "Çekimser", "c"),
              ("KATILMADI", "Katılmadı", "x")]


# ---------- Yardımcılar ----------

def tr_title(s: str) -> str:
    """Türkçe kurallarına uygun başlık harfi: 'ALİ MAHİR BAŞARIR' -> 'Ali Mahir Başarır'."""
    return " ".join(w[:1] + w[1:].replace("I", "ı").replace("İ", "i").lower() for w in s.split(" "))


def slug(s: str) -> str:
    tr = str.maketrans("ÇĞİÖŞÜÂÎÛçğıöşüâîû", "CGIOSUAIUcgiosuaiu")
    return re.sub(r"[^a-z0-9]+", "-", s.translate(tr).lower()).strip("-")


def inline(s: str) -> str:
    return NOTE_RE.sub(lambda m: f'<span class="sahne">{m.group(0)}</span>', escape(s))


def parse_date(tarih: str) -> datetime | None:
    m = re.match(r"(\d{1,2}) (\S+) (\d{4})", tarih)
    if m and m.group(2) in AYLAR:
        return datetime(int(m.group(3)), AYLAR.index(m.group(2)) + 1, int(m.group(1)))
    return None


def tarih_yazi(d: datetime) -> str:
    return f"{d.day} {AYLAR[d.month - 1]} {d.year} {GUNLER[d.weekday()]}"


def durum_kodu(durum: str) -> str:
    d = durum.lower()
    return "basilmis" if d.startswith("bas") else "tam" if d.startswith("tam") else "ham"


def oy_kodu(s: str) -> str:
    s = s.upper()
    return "RET" if s in ("RED", "RET") else s


def short(s: str, n: int = 190) -> str:
    """Uzun karar cümlesini kısaltır ama sondaki hükmü korur."""
    if len(s) <= n:
        return s
    v = VERDICT_RE.search(s)
    tail = s[v.start():] if v else ""
    head = s[: n - len(tail) - 3].rsplit(" ", 1)[0]
    return f"{head} … {tail}"


def decisions(ozet: str) -> list[str]:
    """Özetteki karar cümleleri (kabul edildi / edilmedi / ertelendi ...)."""
    return [ln.strip() for ln in ozet.split("\n") if len(ln) > 40 and VERDICT_RE.search(ln.strip())]


# ---------- Tutanak metni ayrıştırma ----------

def parse(text: str) -> dict:
    """Tutanak metnini bloklara ayırır: ön bilgi, başlıklar, konuşmalar, notlar."""
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln and not NOISE_RE.match(ln)]
    start = next((i for i, ln in enumerate(lines) if OTURUM_RE.match(ln)), 0)
    front, body = lines[:start], lines[start:]

    blocks, toc, speakers = [], [], OrderedDict()
    last_place: dict[str, str] = {}
    words = 0
    for ln in body:
        words += len(ln.split())
        if OTURUM_RE.match(ln):
            toc.append(("oturum", ln, len(blocks)))
            blocks.append(("oturum", ln))
            continue
        if AGENDA_RE.match(ln) and len(ln) < 600:
            toc.append(("gundem", ln, len(blocks)))
            blocks.append(("gundem", ln))
            continue
        m = SPEAKER_RE.match(ln)
        if m and len(m.group(1)) < 80:
            name, place, rest = m.group(1).strip(), (m.group(2) or "").strip(), m.group(3)
            role = ""
            rm = re.match(r"^(.+? ADINA) (.+)$", name)
            if rm:  # "CHP GRUBU ADINA CEM AVŞAR" -> kişi + rol
                role, name = tr_title(rm.group(1)).replace(" Adına", " adına"), rm.group(2)
            devam = place.lower() == "devamla"
            if devam:
                place = last_place.get(name, "")
            elif place:
                last_place[name] = place
            sid = slug(name)
            sp = speakers.setdefault(sid, {"name": name, "place": place, "count": 0, "words": 0})
            sp["count"] += 1
            sp["words"] += len(rest.split())
            if place and not sp["place"]:
                sp["place"] = place
            blocks.append(("soz", name, place, devam, rest, sid, role))
            continue
        if ln.startswith("(") and ln.endswith(")"):
            blocks.append(("not", ln))
        elif blocks and blocks[-1][0] in ("soz", "devam"):
            blocks.append(("devam", ln))
        else:
            blocks.append(("p", ln))
    return {"front": front, "blocks": blocks, "toc": toc, "speakers": speakers, "words": words}


# ---------- Oylama özetleri ----------

def vote_counts(v: dict) -> Counter:
    return Counter(oy_kodu(o[6]) for o in v["oylar"])


def party_table(v: dict) -> list[tuple[str, Counter]]:
    by: dict[str, Counter] = {}
    for o in v["oylar"]:
        by.setdefault(PARTI_KISA.get(o[3], o[3]), Counter())[oy_kodu(o[6])] += 1
    return sorted(by.items(), key=lambda kv: -sum(kv[1].values()))


def bar(c: Counter, total: int | None = None) -> str:
    total = total or sum(c.values()) or 1
    segs = "".join(f'<i class="{cls}" style="width:{c.get(code, 0) / total * 100:.2f}%"></i>'
                   for code, _, cls in OY_TURLERI if c.get(code))
    return f'<span class="bar">{segs}</span>'


def sonuc_cls(sonuc: str) -> str:
    s = sonuc.lower()
    return "red" if ("edilme" in s or "redd" in s) else "ok" if s else "na"


# ---------- Ortak şablon ----------

CSS = """
:root{--bg:#f7f5f1;--panel:#fff;--ink:#1d1b18;--muted:#6b665e;--line:#e4dfd6;--accent:#a3122a;
--accent-soft:#f6e3e6;--ham:#9a6400;--ham-bg:#fbf0d9;--bas:#2c6e3f;--bas-bg:#e2f1e6;--mark:#ffe58a;
--k:#2f8a4f;--r:#c0392b;--c:#d39b1c;--x:#cfc9bf;--oy:#3b5bab;--oy-bg:#e5eaf7;
--serif:Georgia,Cambria,"Times New Roman",serif;--sans:"Segoe UI",system-ui,-apple-system,sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#151412;--panel:#1e1c1a;--ink:#ece8e1;--muted:#a19a8f;
--line:#34302b;--accent:#ff7b8c;--accent-soft:#3a1f24;--ham:#f0c060;--ham-bg:#3a2e14;--bas:#7fd197;
--bas-bg:#1b3324;--mark:#7a6312;--k:#5cc17f;--r:#ec6a5c;--c:#e8b84a;--x:#4a453f;--oy:#9db4ee;--oy-bg:#222b40}}
*{box-sizing:border-box}[hidden]{display:none!important}html{scroll-padding-top:90px}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--sans)}
a{color:inherit}
.pill{display:inline-block;font-size:12px;font-weight:600;padding:2px 9px;border-radius:99px;letter-spacing:.02em;white-space:nowrap}
.pill.ham{color:var(--ham);background:var(--ham-bg)}.pill.tam,.pill.basilmis,.pill.ok{color:var(--bas);background:var(--bas-bg)}
.pill.red{color:var(--r);background:var(--accent-soft)}.pill.na{color:var(--muted);background:var(--line)}
.pill.oy{color:var(--oy);background:var(--oy-bg)}.pill.yeni{color:#fff;background:var(--accent)}
.bar{display:flex;height:8px;border-radius:4px;overflow:hidden;background:var(--line);min-width:60px}
.bar i{display:block;height:100%}.bar .k{background:var(--k)}.bar .r{background:var(--r)}
.bar .c{background:var(--c)}.bar .x{background:var(--x)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:baseline}
.dot.k{background:var(--k)}.dot.r{background:var(--r)}.dot.c{background:var(--c)}.dot.x{background:var(--x)}
input[type=search]{font:inherit;padding:8px 12px;border:1px solid var(--line);border-radius:8px;
background:var(--panel);color:var(--ink);width:100%}
button{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--panel);color:var(--ink);
border-radius:8px;padding:6px 12px}button:hover{border-color:var(--muted)}
.chips{display:flex;gap:6px;flex-wrap:wrap}.chips button{border-radius:99px;padding:4px 12px;font-size:13px}
.chips button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
"""

READ_JS = """
const K='tbmm-okundu';
function okunanlar(){try{return JSON.parse(localStorage.getItem(K)||'{}')}catch(e){return {}}}
function okundu(id){try{const o=okunanlar();o[id]=Date.now();localStorage.setItem(K,JSON.stringify(o))}catch(e){}}
"""


def page(title: str, css: str, body: str, js: str) -> str:
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{CSS}{css}</style></head><body>{body}
<script>{READ_JS}{js}</script></body></html>"""


TOPBAR_CSS = """
.top{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line)}
.bar-in{max-width:1240px;margin:0 auto;padding:10px 16px;display:flex;gap:12px;align-items:center}
.home{text-decoration:none;color:var(--muted);white-space:nowrap}.home:hover{color:var(--accent)}
.head h1{font-family:var(--serif);font-weight:normal;font-size:32px;margin:0;line-height:1.2}
.head .sub{color:var(--muted);margin:8px 0 12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.links{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;margin-bottom:8px}.links a{color:var(--accent)}
.box{margin-top:14px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;font-size:14px}
.box summary{cursor:pointer;font-weight:600}.box ul{margin:10px 0 0;padding-left:18px}.box li{margin-bottom:8px}
.box a{color:var(--accent)}
"""


# ---------- Ana sayfa (zaman çizelgesi) ----------

def build_index(sessions: list[dict], votes: list[dict], updated: str) -> str:
    entries = []  # (tarih, saat, html, tür)
    for s in sessions:
        dcls = durum_kodu(s["durum"])
        top = ", ".join(escape(n) for n in s["top_names"][:4])
        q = escape(f"tutanak {s['birlesim']} {s['tarih']} {s['durum']} {s['ozet_flat']} {' '.join(s['top_names'])}".lower())
        meta = (f"{s['n_speakers']} konuşmacı · ~{s['minutes']} dk okuma" if s["has_text"] else "Metin yalnızca PDF olarak var")
        if s["n_votes"]:
            meta += f" · {s['n_votes']} açık oylama"
        if top:
            meta += " · " + top
        html_ = f"""
<a class="card" href="{s['page']}" data-id="{s['read_id']}" data-tur="tutanak" data-q="{q}">
  <div class="ico tut">T</div>
  <div class="mid">
    <div class="row1"><b>{s['birlesim']}. Birleşim tutanağı</b>
      <span class="pill {dcls}">{escape(s['durum'])}</span><span class="pill yeni" hidden>Yeni</span></div>
    <div class="lead">{escape(s['lead']) or '&nbsp;'}</div>
    <div class="meta">{meta}</div>
  </div>
</a>"""
        entries.append((s["date"], "", html_, s["donem"], s["yil"], s["birlesim"], 0))

    for v in votes:
        c = vote_counts(v)
        q = escape(f"oylama {v['birlesim']} {v['tarih_yazi']} {v['baslik']} {v['sonuc']} {v['sira_sayisi']}".lower())
        saat = v["baslangic"][11:16] if v["baslangic"] else ""
        nums = " · ".join(f'<span class="dot {cls}"></span>{c.get(code, 0)} {lbl.lower()}'
                          for code, lbl, cls in OY_TURLERI if c.get(code) or code != "ÇEKİMSER")
        html_ = f"""
<a class="card" href="{v['page']}" data-id="{v['read_id']}" data-tur="oylama" data-q="{q}">
  <div class="ico oyl">O</div>
  <div class="mid">
    <div class="row1"><b>Açık oylama</b>{f'<span class="saat">{saat}</span>' if saat else ''}
      <span class="pill {sonuc_cls(v['sonuc'])}">{escape(v['sonuc'] or 'Sonuç belirtilmemiş')}</span>
      <span class="pill yeni" hidden>Yeni</span></div>
    <div class="lead">{escape(v['baslik'])}</div>
    {bar(c)}
    <div class="meta">{nums} · {v['birlesim']}. Birleşim</div>
  </div>
</a>"""
        entries.append((v["date"], saat, html_, v["donem"], v["yil"], v["birlesim"], v["no"]))

    # En yeni gün en üstte; gün içinde en geç saatteki oylama üstte, tutanak günün sonunda
    entries.sort(key=lambda e: (e[0], e[3], e[4], e[5], e[1], e[6]), reverse=True)
    days: OrderedDict[datetime, list[str]] = OrderedDict()
    for e in entries:
        days.setdefault(e[0], []).append(e[2])
    sections = "".join(
        f'<section><h2>{escape(tarih_yazi(d) if d != datetime.min else "Tarihsiz")}</h2>{"".join(cards)}</section>'
        for d, cards in days.items())

    css = TOPBAR_CSS + """
.wrap{max-width:860px;margin:0 auto;padding:32px 16px 64px}
header h1{font-family:var(--serif);font-weight:normal;font-size:32px;margin:0 0 4px}
header p{color:var(--muted);margin:0 0 20px}
.tools{display:flex;flex-direction:column;gap:10px;margin-bottom:8px}
.tools .row{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.tools label{white-space:nowrap;color:var(--muted);font-size:14px;display:flex;gap:6px;align-items:center}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:32px 0 10px;font-weight:600}
.card{display:flex;gap:16px;background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:14px 18px;margin-bottom:10px;text-decoration:none;transition:border-color .15s}
.card:hover{border-color:var(--accent)}.card.unread{border-left:4px solid var(--accent)}
.ico{flex:none;width:34px;height:34px;border-radius:9px;display:grid;place-items:center;font:600 14px var(--sans)}
.ico.tut{background:var(--accent-soft);color:var(--accent)}.ico.oyl{background:var(--oy-bg);color:var(--oy)}
.mid{flex:1;min-width:0}.mid .bar{margin:6px 0 4px;max-width:360px}
.row1{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.saat{color:var(--muted);font-size:13px}
.lead{margin:4px 0;font-size:14px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.meta{font-size:13px;color:var(--muted)}
.empty{color:var(--muted);text-align:center;padding:40px}
@media (max-width:560px){.card{gap:12px;padding:12px 14px}}
"""
    body = f"""<div class="wrap">
<header><h1>Meclis Tutanakları</h1>
<p>TBMM Genel Kurul · {len(sessions)} tutanak · {len(votes)} açık oylama · son güncelleme {escape(updated)}</p></header>
<div class="tools"><input type="search" id="q" placeholder="Konu, kanun teklifi, milletvekili, tarih, birleşim no…">
<div class="row"><div class="chips" id="tur"><button class="on" data-v="">Tümü</button>
<button data-v="tutanak">Tutanaklar</button><button data-v="oylama">Oylamalar</button></div>
<label><input type="checkbox" id="sadeceYeni"> Sadece okunmamışlar</label></div></div>
{sections or '<p class="empty">Henüz tutanak yok.</p>'}
<p class="empty" id="yok" hidden>Eşleşen kayıt yok.</p>
</div>"""
    js = """
const cards=[...document.querySelectorAll('.card')];let tur='';
try{tur=sessionStorage.getItem('tbmm-tur')||''}catch(e){}
function render(){const o=okunanlar(),q=document.getElementById('q').value.toLocaleLowerCase('tr').trim(),
 y=document.getElementById('sadeceYeni').checked;let n=0;
 document.querySelectorAll('#tur button').forEach(b=>b.classList.toggle('on',b.dataset.v===tur));
 cards.forEach(c=>{const unread=!o[c.dataset.id];c.classList.toggle('unread',unread);
  c.querySelector('.yeni').hidden=!unread;
  const show=(!q||q.split(/\\s+/).every(w=>c.dataset.q.includes(w)))&&(!y||unread)&&(!tur||c.dataset.tur===tur);
  c.hidden=!show;if(show)n++});
 document.querySelectorAll('section').forEach(s=>s.hidden=![...s.querySelectorAll('.card')].some(c=>!c.hidden));
 document.getElementById('yok').hidden=n>0||!cards.length}
document.getElementById('q').addEventListener('input',render);
document.getElementById('sadeceYeni').addEventListener('change',render);
document.querySelectorAll('#tur button').forEach(b=>b.onclick=()=>{tur=b.dataset.v;
 try{sessionStorage.setItem('tbmm-tur',tur)}catch(e){}render()});
window.addEventListener('pageshow',render);render();
"""
    return page("Meclis Tutanakları", css, body, js)


# ---------- Tutanak okuma sayfası ----------

def build_reader(s: dict, prev: dict | None, nxt: dict | None) -> str:
    doc, out = s["doc"], []
    for b in doc["blocks"]:
        kind = b[0]
        if kind == "oturum":
            out.append(f'<h2 class="oturum" id="b{len(out)}">{escape(b[1])}</h2>')
        elif kind == "gundem":
            out.append(f'<h3 class="gundem" id="b{len(out)}">{escape(b[1])}</h3>')
        elif kind == "soz":
            _, name, place, devam, rest, sid, role = b
            who = escape(name) + (f' <span class="yer">({escape(place)})</span>' if place else "")
            if role:
                who += f' <span class="yer">· {escape(role)}</span>'
            if devam:
                who += ' <span class="yer">· devamla</span>'
            cls = "soz baskan" if name == "BAŞKAN" else "soz"
            out.append(f'<p class="{cls}" data-s="{sid}" id="b{len(out)}"><span class="kim">{who}</span> {inline(rest)}</p>')
        elif kind == "devam":
            out.append(f'<p class="devam" id="b{len(out)}">{inline(b[1])}</p>')
        elif kind == "not":
            out.append(f'<p class="not" id="b{len(out)}">{escape(b[1])}</p>')
        else:
            out.append(f'<p id="b{len(out)}">{inline(b[1])}</p>')

    # blok indeksleri id'lerle bire bir aynı (her blok tek eleman üretiyor)
    toc_html = "".join(
        f'<a class="t-{k}" href="#b{i}">{escape(t if len(t) < 140 else t[:137] + "…")}</a>'
        for k, t, i in doc["toc"]) or '<p class="bos">Bu tutanakta başlık yok.</p>'
    sps = sorted(doc["speakers"].items(), key=lambda kv: -kv[1]["words"])
    sp_html = "".join(
        f'<button class="sp" data-s="{sid}" title="Sonraki konuşmasına git">'
        f'<span>{escape(tr_title(sp["name"]))}<small>{escape(sp["place"])}</small></span><em>{sp["count"]}</em></button>'
        for sid, sp in sps)

    front = ""
    if doc["front"]:
        front = ('<details class="front"><summary>Kapak, içindekiler ve ön bilgiler</summary>'
                 + "".join(f"<p>{escape(x)}</p>" for x in doc["front"]) + "</details>")
    if not s["has_text"]:
        pdf = s["src"].get("pdf")
        front = ('<p class="bos">Bu dönemin tutanağı TBMM tarafından yalnızca PDF olarak yayınlanmış. '
                 + (f'<a href="{escape(pdf)}" target="_blank" rel="noopener">PDF\'i aç ↗</a>' if pdf else "") + "</p>")

    ozet_html = "".join(f"<p>{escape(x)}</p>" for x in s["ozet"].split("\n") if x.strip()) \
        or '<p class="bos">Bu birleşim için özet yayınlanmamış.</p>'

    links = [f'<a href="{escape(s["tbmm_url"])}" target="_blank" rel="noopener">TBMM sayfası ↗</a>']
    for key, label in (("pdf", "PDF ↗"), ("docx", "Word ↗")):
        if s["src"].get(key):
            links.append(f'<a href="{escape(s["src"][key])}" target="_blank" rel="noopener">{label}</a>')

    karar_html = ""
    if s["decisions"]:
        karar_html = (f'<details class="box" open><summary>Bu birleşimde alınan kararlar ({len(s["decisions"])})'
                      '</summary><ul>' + "".join(f"<li>{escape(d)}</li>" for d in s["decisions"]) + "</ul></details>")
    oy_html = ""
    if s["votes"]:
        oy_html = (f'<details class="box" open><summary>Açık oylamalar ({len(s["votes"])})</summary><ul>'
                   + "".join(f'<li><a href="{v["page"]}">{escape(v["baslik"])}</a> '
                             f'<span class="pill {sonuc_cls(v["sonuc"])}">{escape(v["sonuc"] or "?")}</span></li>'
                             for v in s["votes"]) + "</ul></details>")

    nav_prev = f'<a href="{prev["page"]}">← {prev["birlesim"]}. Birleşim</a>' if prev else ""
    nav_next = f'<a href="{nxt["page"]}">{nxt["birlesim"]}. Birleşim →</a>' if nxt else ""
    dcls = durum_kodu(s["durum"])
    ham_not = "" if dcls != "ham" else (
        '<p class="uyari">Ham tutanak: stenograflarca deşifre edilmiş, henüz uzman kontrolünden geçmemiş metin. '
        'Kesin hâli (Tam/Basılmış) yayınlanınca otomatik olarak güncellenecek.</p>')

    css = TOPBAR_CSS + """
.find{display:flex;gap:6px;align-items:center;margin-left:auto;width:min(420px,60%)}
.find span{font-size:13px;color:var(--muted);white-space:nowrap;min-width:52px;text-align:right}
.find button{padding:6px 10px}
.layout{max-width:1240px;margin:0 auto;padding:0 16px;display:grid;grid-template-columns:280px minmax(0,1fr);gap:40px}
aside{position:sticky;top:62px;align-self:start;max-height:calc(100vh - 62px);overflow:auto;padding:24px 4px 40px 0}
aside h4{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:22px 0 8px}
aside a{display:block;text-decoration:none;font-size:13px;padding:4px 8px;border-radius:6px;color:var(--ink)}
aside a:hover{background:var(--accent-soft)}
aside .t-oturum{font-weight:600;margin-top:6px}aside .t-gundem{padding-left:16px;color:var(--muted)}
.sp{display:flex;justify-content:space-between;align-items:center;width:100%;text-align:left;border:0;
background:none;padding:5px 8px;border-radius:6px;font-size:13px;gap:8px}
.sp:hover,.sp.on{background:var(--accent-soft)}
.sp small{display:block;color:var(--muted);font-size:11px}.sp em{font-style:normal;color:var(--muted);font-size:12px}
main{padding:28px 0 120px;max-width:760px}
.uyari{font-size:13px;background:var(--ham-bg);color:var(--ink);border-radius:8px;padding:10px 12px}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:22px 0 8px}
.tabs button{border:0;border-bottom:2px solid transparent;border-radius:0;background:none;padding:8px 14px;color:var(--muted)}
.tabs button.on{border-bottom-color:var(--accent);color:var(--ink);font-weight:600}
.metin{font-family:var(--serif);font-size:var(--fs,18px);line-height:1.7}
.metin p{margin:0 0 .9em}
.metin .kim{font-family:var(--sans);font-weight:700;font-size:.78em;letter-spacing:.02em;color:var(--accent)}
.metin .baskan .kim{color:var(--muted)}.metin .yer{font-weight:400;color:var(--muted)}
.metin .sahne,.metin .not{color:var(--muted);font-style:italic}
.metin .oturum{font-family:var(--sans);font-size:14px;letter-spacing:.12em;text-align:center;color:var(--muted);
margin:48px 0 24px;padding-top:24px;border-top:1px solid var(--line)}
.metin .gundem{font-family:var(--sans);font-size:16px;margin:32px 0 14px;line-height:1.4}
.metin .flash{background:var(--accent-soft);border-radius:4px;box-shadow:0 0 0 6px var(--accent-soft)}
mark{background:var(--mark);color:inherit;border-radius:2px}mark.cur{outline:2px solid var(--accent)}
.front{font-size:.85em;color:var(--muted);margin-bottom:24px}.front summary{cursor:pointer;font-family:var(--sans);font-size:14px}
.bos{color:var(--muted)}.bos a{color:var(--accent)}
.foot{display:flex;justify-content:space-between;margin-top:48px;padding-top:20px;border-top:1px solid var(--line)}
.foot a{color:var(--accent);text-decoration:none}
.fs{display:flex;gap:4px}.fs button{padding:4px 9px}
#asideToggle{display:none}
@media (max-width:900px){.layout{grid-template-columns:1fr;gap:0}
aside{display:none;position:static;max-height:none;padding:8px 0}aside.open{display:block}
#asideToggle{display:inline-block}.find{width:auto;flex:1}.home b{display:none}}
"""
    body = f"""<div class="top"><div class="bar-in">
<a class="home" href="index.html">← <b>Tüm kayıtlar</b></a>
<button id="asideToggle">İçindekiler</button>
<div class="find"><input type="search" id="q" placeholder="Metinde ara…"><span id="cnt"></span>
<button id="prevM" title="Önceki">↑</button><button id="nextM" title="Sonraki (Enter)">↓</button></div>
</div></div>
<div class="layout">
<aside id="aside"><h4>İçindekiler</h4>{toc_html}<h4>Konuşmacılar ({len(sps)})</h4>{sp_html}</aside>
<main>
<div class="head"><h1>{s['birlesim']}. Birleşim</h1>
<div class="sub"><span>{escape(s['tarih'])}</span><span class="pill {dcls}">{escape(s['durum'])}</span>
<span>{s['donem']}. Dönem {s['yil']}. Yasama Yılı{f" · ~{s['minutes']} dk okuma" if s['has_text'] else ''}</span></div>
<div class="links">{''.join(links)}</div>{ham_not}{oy_html}{karar_html}</div>
<div class="tabs"><button class="on" data-tab="metin">Tutanak</button><button data-tab="ozet">Özet</button>
<span style="flex:1"></span><div class="fs"><button data-fs="-1" title="Yazıyı küçült">A−</button><button data-fs="1" title="Yazıyı büyüt">A+</button></div></div>
<div class="metin" id="metin">{front}{''.join(out)}</div>
<div class="metin" id="ozet" hidden>{ozet_html}</div>
<div class="foot"><span>{nav_prev}</span><span>{nav_next}</span></div>
</main></div>"""
    js = f"""okundu({json.dumps(s['read_id'])});
document.querySelectorAll('.tabs [data-tab]').forEach(b=>b.onclick=()=>{{
 document.querySelectorAll('.tabs [data-tab]').forEach(x=>x.classList.toggle('on',x===b));
 document.getElementById('metin').hidden=b.dataset.tab!=='metin';
 document.getElementById('ozet').hidden=b.dataset.tab!=='ozet';doSearch()}});
let fs=18;try{{fs=+localStorage.getItem('tbmm-fs')||18}}catch(e){{}}
const setFs=()=>{{document.documentElement.style.setProperty('--fs',fs+'px');try{{localStorage.setItem('tbmm-fs',fs)}}catch(e){{}}}};setFs();
document.querySelectorAll('[data-fs]').forEach(b=>b.onclick=()=>{{fs=Math.min(26,Math.max(14,fs+ +b.dataset.fs));setFs()}});
document.getElementById('asideToggle').onclick=()=>document.getElementById('aside').classList.toggle('open');
const showText=()=>{{if(document.getElementById('metin').hidden)document.querySelector('[data-tab=metin]').click()}};
document.querySelectorAll('aside a').forEach(a=>a.addEventListener('click',()=>{{showText();document.getElementById('aside').classList.remove('open')}}));
const pos={{}};
document.querySelectorAll('.sp').forEach(b=>b.onclick=()=>{{showText();
 const list=[...document.querySelectorAll('#metin p[data-s="'+b.dataset.s+'"]')];if(!list.length)return;
 pos[b.dataset.s]=((pos[b.dataset.s]??-1)+1)%list.length;const el=list[pos[b.dataset.s]];
 document.querySelectorAll('.sp').forEach(x=>x.classList.toggle('on',x===b));
 b.querySelector('em').textContent=(pos[b.dataset.s]+1)+'/'+list.length;flash(el)}});
function flash(el){{el.scrollIntoView({{block:'center',behavior:'smooth'}});el.classList.add('flash');setTimeout(()=>el.classList.remove('flash'),1600)}}
let marks=[],cur=-1,timer;
function clearMarks(){{marks.forEach(m=>{{const p=m.parentNode;p.replaceChild(document.createTextNode(m.textContent),m);p.normalize()}});marks=[];cur=-1}}
const norm=s=>s.toLocaleLowerCase('tr');
function doSearch(){{clearMarks();const q=norm(document.getElementById('q').value.trim());const cnt=document.getElementById('cnt');
 if(q.length<2){{cnt.textContent='';return}}
 const root=document.getElementById('metin').hidden?document.getElementById('ozet'):document.getElementById('metin');
 const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);const nodes=[];while(w.nextNode())nodes.push(w.currentNode);
 for(const n of nodes){{const t=n.textContent,l=norm(t);if(l.length!==t.length)continue;let i=l.indexOf(q);if(i<0)continue;
  const f=document.createDocumentFragment();let last=0;
  while(i>=0){{f.append(t.slice(last,i));const m=document.createElement('mark');m.textContent=t.slice(i,i+q.length);f.append(m);marks.push(m);last=i+q.length;i=l.indexOf(q,last)}}
  f.append(t.slice(last));n.parentNode.replaceChild(f,n)}}
 cnt.textContent=marks.length?'':'0 sonuç';if(marks.length)go(1)}}
function go(d){{if(!marks.length)return;if(cur>=0)marks[cur].classList.remove('cur');
 cur=(cur+d+marks.length)%marks.length;marks[cur].classList.add('cur');
 marks[cur].scrollIntoView({{block:'center'}});document.getElementById('cnt').textContent=(cur+1)+' / '+marks.length}}
document.getElementById('q').addEventListener('input',()=>{{clearTimeout(timer);timer=setTimeout(doSearch,250)}});
document.getElementById('q').addEventListener('keydown',e=>{{if(e.key==='Enter'){{e.preventDefault();go(e.shiftKey?-1:1)}}}});
document.getElementById('nextM').onclick=()=>go(1);document.getElementById('prevM').onclick=()=>go(-1);
document.addEventListener('keydown',e=>{{if((e.ctrlKey||e.metaKey)&&e.key==='f'){{e.preventDefault();document.getElementById('q').focus();document.getElementById('q').select()}}}});
"""
    return page(f"{s['birlesim']}. Birleşim · {s['tarih']}", css, body, js)


# ---------- Oylama sayfası ----------

def build_vote(v: dict, s: dict) -> str:
    c = vote_counts(v)
    total = sum(c.values())
    say = v.get("sayilar", {})
    resmi = [("Kabul", say.get("kabul")), ("Ret", say.get("ret")), ("Çekimser", say.get("cekimser")),
             ("Boş", say.get("bos")), ("Geçersiz", say.get("gecersiz")), ("Mükerrer", say.get("mukerrer")),
             ("Toplam oy", say.get("toplam"))]
    resmi_html = "".join(f"<div><b>{n}</b><span>{lbl}</span></div>" for lbl, n in resmi if n is not None)

    party_rows = []
    for party, pc in party_table(v):
        n = sum(pc.values())
        cells = "".join(f'<td class="num">{pc.get(code, 0) or ""}</td>' for code, _, _ in OY_TURLERI)
        party_rows.append(f"<tr><th>{escape(party)}</th>{cells}<td class='num muted'>{n}</td><td class='barcell'>{bar(pc, n)}</td></tr>")

    rows = []
    for o in v["oylar"]:
        il, soyad, ad, parti, sistem, pusula, sonuc, tarih, saat = o
        code = oy_kodu(sonuc)
        cls = next((c3 for c1, _, c3 in OY_TURLERI if c1 == code), "x")
        pus = f' <small title="Pusula ile">(pusula)</small>' if pusula not in ("-", "") else ""
        rows.append(f'<tr data-v="{escape(code)}"><td>{escape(tr_title(ad))} {escape(soyad)}</td>'
                    f'<td>{escape(tr_title(il))}</td><td>{escape(PARTI_KISA.get(parti, parti))}</td>'
                    f'<td><span class="dot {cls}"></span>{escape(tr_title(code))}{pus}</td>'
                    f'<td class="muted">{escape(saat if saat[:1].isdigit() else "")}</td></tr>')

    chips = '<button class="on" data-v="">Tümü</button>' + "".join(
        f'<button data-v="{code}"><span class="dot {cls}"></span>{lbl} ({c.get(code, 0)})</button>'
        for code, lbl, cls in OY_TURLERI if c.get(code))
    head_cells = "".join(f"<th class='num'><span class='dot {cls}'></span>{lbl}</th>" for _, lbl, cls in OY_TURLERI)

    links = [f'<a href="{escape(v["kaynak"])}" target="_blank" rel="noopener">TBMM oylama sayfası ↗</a>']
    if s:
        links.insert(0, f'<a href="{s["page"]}">{v["birlesim"]}. Birleşim tutanağı</a>')
    saat = v["baslangic"][11:16] if v["baslangic"] else ""

    css = TOPBAR_CSS + """
main{max-width:980px;margin:0 auto;padding:28px 16px 100px}
.head h1{font-size:26px}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}
.stats div{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 14px;min-width:84px}
.stats b{display:block;font-size:20px;font-weight:600}.stats span{font-size:12px;color:var(--muted)}
.bigbar .bar{height:14px;border-radius:7px}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin-top:6px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:34px 0 10px;font-weight:600}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:14px}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line)}
thead th{font-size:12px;color:var(--muted);font-weight:600;background:var(--bg)}
tbody th{font-weight:600}.num{text-align:right;font-variant-numeric:tabular-nums}.muted{color:var(--muted)}
.barcell{width:30%}.scroll{overflow-x:auto}
.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.filters input{max-width:320px}
small{color:var(--muted)}
@media (max-width:640px){.barcell{display:none}.hide-sm{display:none}}
"""
    body = f"""<div class="top"><div class="bar-in"><a class="home" href="index.html">← <b>Tüm kayıtlar</b></a></div></div>
<main>
<div class="head"><div class="sub" style="margin:0 0 8px"><span class="pill oy">Açık oylama</span>
<span class="pill {sonuc_cls(v['sonuc'])}">{escape(v['sonuc'] or 'Sonuç belirtilmemiş')}</span>
{f"<span class='muted'>{escape(v['bolum'])}</span>" if v['bolum'] else ''}</div>
<h1>{escape(v['baslik'])}</h1>
<div class="sub"><span>{escape(v['tarih_yazi'])}{f' · {saat}' if saat else ''}</span>
<span>{v['donem']}. Dönem {v['yil']}. Yasama Yılı · {v['birlesim']}. Birleşim</span>
{f"<span>Sıra sayısı {escape(v['sira_sayisi'])}</span>" if v['sira_sayisi'] else ''}</div>
<div class="links">{''.join(links)}</div></div>
<div class="stats">{resmi_html}</div>
<div class="bigbar">{bar(c, total)}<div class="legend">{''.join(f'<span><span class="dot {cls}"></span>{lbl} {c.get(code, 0)}</span>' for code, lbl, cls in OY_TURLERI)}</div></div>
<h2>Partilere göre</h2>
<div class="scroll"><table><thead><tr><th>Parti</th>{head_cells}<th class="num">Üye</th><th class="barcell"></th></tr></thead>
<tbody>{''.join(party_rows)}</tbody></table></div>
<h2>Milletvekilleri ({len(v['oylar'])})</h2>
<div class="filters"><input type="search" id="q" placeholder="İsim, il veya parti ara…"><div class="chips" id="oy">{chips}</div></div>
<div class="scroll"><table id="liste"><thead><tr><th>Milletvekili</th><th>İl</th><th>Parti</th><th>Oy</th><th>Saat</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="muted" id="sayac"></p>
</main>"""
    js = f"""okundu({json.dumps(v['read_id'])});
const rows=[...document.querySelectorAll('#liste tbody tr')];let oy='';
rows.forEach(r=>r.dataset.q=r.textContent.toLocaleLowerCase('tr'));
function f(){{const q=document.getElementById('q').value.toLocaleLowerCase('tr').trim();let n=0;
 rows.forEach(r=>{{const s=(!oy||r.dataset.v===oy)&&(!q||q.split(/\\s+/).every(w=>r.dataset.q.includes(w)));r.hidden=!s;if(s)n++}});
 document.getElementById('sayac').textContent=n+' milletvekili gösteriliyor'}}
document.getElementById('q').addEventListener('input',f);
document.querySelectorAll('#oy button').forEach(b=>b.onclick=()=>{{oy=b.dataset.v;
 document.querySelectorAll('#oy button').forEach(x=>x.classList.toggle('on',x===b));f()}});f();
"""
    return page(f"Oylama · {v['baslik'][:60]}", css, body, js)


# ---------- Ana akış ----------

def collect() -> tuple[list[dict], list[dict]]:
    sessions, votes = [], []
    for meta_path in DATA.glob("donem*/yil*/birlesim*/meta.json"):
        folder = meta_path.parent
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        base = f"d{meta['donem']}-y{meta['yil']}-b{meta['birlesim']:03d}"
        txt = folder / "tutanak.txt"
        ozet = (folder / "ozet.txt").read_text(encoding="utf-8") if (folder / "ozet.txt").exists() else ""
        doc = parse(txt.read_text(encoding="utf-8")) if txt.exists() else \
            {"front": [], "blocks": [], "toc": [], "speakers": {}, "words": 0}
        named = [x for x in doc["speakers"].values() if x["name"] != "BAŞKAN"]
        dec = decisions(ozet)
        opening = next((ln.strip() for ln in ozet.split("\n") if ln.startswith("TBMM Genel Kurulu")), "")
        date = parse_date(meta["tarih"]) or datetime.min
        s = {
            **meta, "page": f"{base}.html", "doc": doc, "ozet": ozet, "has_text": txt.exists(),
            "src": meta.get("kaynaklar", {}),
            "read_id": f"{meta['key']}:{durum_kodu(meta['durum'])}",
            "tbmm_url": f"https://www.tbmm.gov.tr/Tutanaklar/Tutanak?Id={meta['id']}",
            "date": date, "decisions": dec,
            "lead": short(dec[-1]) if dec else opening,
            "ozet_flat": re.sub(r"\s+", " ", ozet),
            "minutes": max(1, round(doc["words"] / 220)),
            "n_speakers": len(named),
            "top_names": [tr_title(x["name"]) for x in sorted(named, key=lambda x: -x["words"])],
            "votes": [],
        }
        oy_path = folder / "oylama.json"
        if oy_path.exists():
            for v in json.loads(oy_path.read_text(encoding="utf-8")):
                vd = datetime.fromisoformat(v["baslangic"][:10]) if v.get("baslangic") else date
                v.update({
                    "donem": meta["donem"], "yil": meta["yil"], "birlesim": meta["birlesim"],
                    "page": f"{base}-o{v['no']}.html",
                    "read_id": f"{meta['key']}:oy{v['no']}",
                    "date": vd, "tarih_yazi": tarih_yazi(vd) if vd != datetime.min else meta["tarih"],
                })
                s["votes"].append(v)
                votes.append(v)
        s["n_votes"] = len(s["votes"])
        sessions.append(s)
    sessions.sort(key=lambda x: (x["date"], x["donem"], x["yil"], x["birlesim"]), reverse=True)
    return sessions, votes


def build() -> Path:
    OUT.mkdir(exist_ok=True)
    sessions, votes = collect()
    by_key = {s["key"]: s for s in sessions}
    written = {"index.html"}
    for i, s in enumerate(sessions):
        newer = sessions[i - 1] if i > 0 else None
        older = sessions[i + 1] if i + 1 < len(sessions) else None
        (OUT / s["page"]).write_text(build_reader(s, older, newer), encoding="utf-8")
        written.add(s["page"])
    for v in votes:
        s = by_key.get(f"{v['donem']}-{v['yil']}-{v['birlesim']}")
        (OUT / v["page"]).write_text(build_vote(v, s), encoding="utf-8")
        written.add(v["page"])
    for p in OUT.glob("*.html"):  # artık var olmayan eski sayfaları temizle
        if p.name not in written:
            p.unlink()
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    index = OUT / "index.html"
    index.write_text(build_index(sessions, votes, datetime.now(TR_TZ).strftime("%d.%m.%Y %H:%M")), encoding="utf-8")
    return index


if __name__ == "__main__":
    print(build())
