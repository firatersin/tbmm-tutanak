#!/usr/bin/env python3
"""data/ klasöründeki tutanak ve oylamalardan statik okuma sitesini üretir (site/ klasörü).

  python arayuz.py        # siteyi yeniden üret

tbmm_tutanak.py her çalıştığında bunu otomatik çağırır. Üretilen site sunucusuz çalışır:
yerelde site/index.html doğrudan açılabilir, GitHub Pages'te de aynen yayınlanır.
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import re
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "site"
STATIC = ROOT / "static"
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


def guvenli_url(u: str | None) -> str:
    """Dış bağlantılar yalnızca TBMM'nin https adreslerine gidebilir (ör. 'javascript:' bağlantıları elenir)."""
    return u if u and re.match(r"^https://([a-z0-9-]+\.)*tbmm\.gov\.tr/", u) else ""


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


# ---------- Parti kırılımı (oy türü -> parti -> milletvekili) ----------

PARTI_RENK = {
    "AK Parti": "#f59e0b", "CHP": "#e53935", "MHP": "#8f2d2d", "DEM Parti": "#7e3fa0", "HDP": "#7e3fa0",
    "YSP": "#7e3fa0", "İYİ Parti": "#29a9e0", "Yeni Yol": "#0f766e", "Yeni Parti": "#4f46e5",
    "YRP": "#15803d", "HÜDA PAR": "#65a30d", "Saadet": "#be185d", "TİP": "#f472b6", "EMEP": "#c2410c",
    "DBP": "#a78bfa", "DSP": "#2563eb", "DP": "#64748b", "DEVA": "#0891b2", "Gelecek": "#0d9488",
    "Bağımsız": "#9ca3af",
}
YEDEK_RENK = ["#84cc16", "#06b6d4", "#d946ef", "#f97316", "#14b8a6", "#a3a3a3"]


def kirilim_html(v: dict) -> str:
    """Oy türü -> parti -> milletvekili kırılımı; çizimi KIRILIM_JS yapar."""
    parties = [p for p, _ in party_table(v)]
    idx = {p: i for i, p in enumerate(parties)}
    colors = [PARTI_RENK.get(p, YEDEK_RENK[i % len(YEDEK_RENK)]) for i, p in enumerate(parties)]
    rows: dict[str, list] = {}
    for il, soyad, ad, parti, _sistem, _pusula, sonuc, _tarih, _saat in v["oylar"]:
        rows.setdefault(oy_kodu(sonuc), []).append(
            [idx[PARTI_KISA.get(parti, parti)], f"{tr_title(ad)} {soyad}", tr_title(il)])
    for lst in rows.values():
        lst.sort(key=lambda r: (r[0], r[1].split(" ")[-1], r[1]))
    data = {"p": [[p, c] for p, c in zip(parties, colors)], "o": rows}
    return f'<div class="kirilim" data-k="{escape(json.dumps(data, ensure_ascii=False, separators=(",", ":")))}"></div>'


KIRILIM_CSS = """
.kirilim{display:flex;flex-direction:column;gap:14px}
.kr-row{display:grid;grid-template-columns:120px 1fr;gap:6px 12px;align-items:center}
.kr-lbl{border:0;background:none;padding:2px 0;text-align:left;font-size:14px;white-space:nowrap}
.kr-lbl b{font-variant-numeric:tabular-nums}.kr-lbl:hover,.kr-lbl.on{color:var(--accent)}
.kr-bar{display:flex;height:22px;border-radius:5px;overflow:hidden;gap:1px;background:var(--line)}
.kr-seg{border:0;border-radius:0;padding:0;min-width:3px;cursor:pointer;opacity:.92}
.kr-seg:hover,.kr-seg.on{opacity:1;outline:2px solid var(--ink);outline-offset:-2px}
.kr-chips{grid-column:2;display:flex;flex-wrap:wrap;gap:4px 6px}
.kr-chip{font-size:12px;padding:1px 8px;border-radius:99px;display:inline-flex;align-items:center;gap:5px}
.kr-chip i{width:8px;height:8px;border-radius:2px;display:inline-block}
.kr-chip.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.kr-row.x .kr-bar{opacity:.55}
.kr-detail{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kr-dh{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.kr-dh b{font-size:15px}.kr-dh span{color:var(--muted);font-size:13px}
.kr-dh input{max-width:240px;padding:5px 10px;margin-left:auto}.kr-dh button{padding:4px 10px;font-size:13px}
.kr-names h5{margin:10px 0 4px;font-size:13px;display:flex;align-items:center;gap:6px}
.kr-names h5 i{width:10px;height:10px;border-radius:2px;display:inline-block}
.kr-names ul{list-style:none;margin:0;padding:0;columns:3 200px;column-gap:18px;font-size:13px}
.kr-names li{break-inside:avoid;padding:1px 0}.kr-names small{color:var(--muted)}
@media (max-width:640px){.kr-row{grid-template-columns:1fr}.kr-chips{grid-column:1}}
"""

KIRILIM_JS = """
const OYT=[['KABUL','Kabul','k'],['RET','Ret','r'],['ÇEKİMSER','Çekimser','c'],['KATILMADI','Katılmadı','x']];
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function kirilim(el){
 const d=JSON.parse(el.dataset.k),P=d.p;let h='';
 for(const [code,lbl,cls] of OYT){const L=d.o[code]||[];if(!L.length)continue;
  const by={};L.forEach(r=>(by[r[0]]=by[r[0]]||[]).push(r));
  const ps=Object.keys(by).map(Number).sort((a,b)=>by[b].length-by[a].length);
  h+=`<div class="kr-row ${cls}"><button class="kr-lbl" data-t="${code}" title="Bu oyu verenlerin hepsini göster"><span class="dot ${cls}"></span>${lbl} <b>${L.length}</b></button>`
   +`<div class="kr-bar">${ps.map(p=>`<button class="kr-seg" data-t="${code}" data-p="${p}" style="flex:${by[p].length};background:${P[p][1]}" title="${esc(P[p][0])}: ${by[p].length}"></button>`).join('')}</div>`
   +`<div class="kr-chips">${ps.map(p=>`<button class="kr-chip" data-t="${code}" data-p="${p}"><i style="background:${P[p][1]}"></i>${esc(P[p][0])} <b>${by[p].length}</b></button>`).join('')}</div></div>`}
 h+='<div class="kr-detail" hidden></div>';el.innerHTML=h;
 const det=el.querySelector('.kr-detail');let cur='';
 function show(t,p){const key=t+'|'+p;
  el.querySelectorAll('.on').forEach(x=>x.classList.remove('on'));
  if(cur===key){cur='';det.hidden=true;return}cur=key;
  el.querySelectorAll(p===''?`.kr-lbl[data-t="${t}"]`:`[data-t="${t}"][data-p="${p}"]`).forEach(x=>x.classList.add('on'));
  const L=(d.o[t]||[]).filter(r=>p===''||r[0]===+p),lbl=OYT.find(o=>o[0]===t)[1];
  const g={};L.forEach(r=>(g[r[0]]=g[r[0]]||[]).push(r));
  det.innerHTML=`<div class="kr-dh"><b>${lbl}${p===''?'':' · '+esc(P[p][0])}</b><span>${L.length} milletvekili</span>`
   +`<input type="search" placeholder="İsim veya il ara…"><button class="kr-x">Kapat</button></div><div class="kr-names">`
   +Object.keys(g).map(Number).sort((a,b)=>g[b].length-g[a].length).map(k=>`<h5><i style="background:${P[k][1]}"></i>${esc(P[k][0])} (${g[k].length})</h5><ul>`
     +g[k].map(r=>`<li data-q="${esc((r[1]+' '+r[2]).toLocaleLowerCase('tr'))}">${esc(r[1])} <small>${esc(r[2])}</small></li>`).join('')+'</ul>').join('')+'</div>';
  det.hidden=false;
  det.querySelector('.kr-x').onclick=()=>show(t,p);
  det.querySelector('input').oninput=e=>{const q=e.target.value.toLocaleLowerCase('tr').trim();
   det.querySelectorAll('li').forEach(li=>li.hidden=!!q&&!li.dataset.q.includes(q));
   det.querySelectorAll('ul').forEach(u=>{u.previousElementSibling.hidden=u.hidden=![...u.children].some(li=>!li.hidden)})};
  det.scrollIntoView({block:'nearest',behavior:'smooth'})}
 el.querySelectorAll('.kr-lbl').forEach(b=>b.onclick=()=>show(b.dataset.t,''));
 el.querySelectorAll('.kr-seg,.kr-chip').forEach(b=>b.onclick=()=>show(b.dataset.t,b.dataset.p));
}
document.querySelectorAll('.kirilim').forEach(kirilim);
"""


# ---------- Oylanan metnin resmi gerekçesi ("Bu oylama neyle ilgili?") ----------

def sira_no(v: dict) -> str:
    no = re.sub(r"\D", "", v.get("sira_sayisi") or "")
    if not no:
        m = re.search(r"S\.\s*Sayısı\s*:\s*(\d+)", v.get("baslik", ""))
        no = m.group(1) if m else ""
    return no


def neyle_ilgili_html(v: dict, compact: bool = False) -> str:
    ss = v.get("ss")
    if not ss or ss.get("bulunamadi"):
        return ""
    no = ss["sira_sayisi"]
    pdf = guvenli_url(ss.get("pdf"))
    kaynak = (f'<a href="{escape(pdf)}" target="_blank" rel="noopener">S. Sayısı {escape(no)} komisyon raporu (PDF) ↗</a>'
              if pdf else f"S. Sayısı {escape(no)}")
    etiketler = []
    esas = re.search(r"\((\d/\d+)\)", ss.get("baslik", ""))
    if ss.get("kanun_no"):
        etiketler.append(f'<span class="pill ok">Kanun No {escape(ss["kanun_no"])}</span>')
    if esas:
        etiketler.append(f'<span class="pill na">Esas No {escape(esas.group(1))}</span>')

    if "buyuk_pdf_mb" in ss:
        govde = (f'<p class="muted">Bu rapor çok büyük ({ss["buyuk_pdf_mb"]} MB, bütçe/kesin hesap gibi) olduğu için '
                 'gerekçesi otomatik çıkarılmadı. Ayrıntılar raporda.</p>')
        return (f'<section class="ilgili"><h2>Bu oylama neyle ilgili?</h2><div class="tags">{"".join(etiketler)}</div>'
                f'{govde}<p class="kaynak">Kaynak: {kaynak}</p></section>') if not compact else ""

    maddeler = ss.get("maddeler", [])
    asil = [m for m in maddeler if not m["rutin"]]
    rutin = [m for m in maddeler if m["rutin"]]
    ana = ss.get("esaslar") or ss.get("amac") or [m["ilk"] for m in asil]
    if not ana and not maddeler:
        return ""

    if compact:
        lis = "".join(f"<li>{escape(x)}</li>" for x in ana[:4])
        more = f'<li class="muted">… <a href="{v["page"]}">devamı oylama sayfasında</a></li>' if len(ana) > 4 else ""
        return f'<div class="ilgili-k"><b>Neyle ilgili:</b><ul>{lis}{more}</ul></div>'

    ana_html = "".join(f"<li>{escape(x)}</li>" for x in ana)
    madde_html = ""
    if asil:
        items = "".join(
            f'<li><details><summary><b>Madde {escape(m["no"])}</b> {escape(m["ilk"])}</summary>'
            f'<p>{escape(m["metin"])}</p></details></li>' for m in asil)
        rutin_not = (f'<p class="muted">Ayrıca {len(rutin)} rutin madde: '
                     + ", ".join(f"Madde {escape(m['no'])}" for m in rutin) + " (tanımlar, yürürlük, yürütme).</p>") if rutin else ""
        madde_html = (f'<details class="maddeler"><summary>Madde madde gerekçeler ({len(asil)} madde)</summary>'
                      f'<ol>{items}</ol>{rutin_not}</details>')
    genel = ss.get("genel_gerekce", "")
    genel_html = ""
    if genel:
        cumleler = [c.strip() for c in SENT_SPLIT.split(genel) if c.strip()]
        paras = [" ".join(cumleler[i:i + 3]) for i in range(0, len(cumleler), 3)]
        genel_html = ('<details class="maddeler"><summary>Genel gerekçenin tamamı</summary>'
                      + "".join(f"<p>{escape(p)}</p>" for p in paras) + "</details>")
    return f"""<section class="ilgili"><h2>Bu oylama neyle ilgili?</h2>
<div class="tags">{''.join(etiketler)}</div>
<ul class="ana">{ana_html}</ul>
{madde_html}{genel_html}
<p class="kaynak">Kaynak: {kaynak}. Maddeler resmi gerekçeden değiştirilmeden alınmıştır. Gerekçe teklifin ilk
hâline aittir; komisyonda veya Genel Kurulda yapılan değişiklikler yansımamış olabilir.</p></section>"""


SENT_SPLIT = re.compile(r"(?<=[a-zçğıöşüâîû\)’'\.]\.)\s+(?=[A-ZÇĞİÖŞÜ\"“(])")

ILGILI_CSS = """
.ilgili{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:18px 0 6px}
.ilgili h2{margin:0 0 8px!important}
.ilgili .tags{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.ilgili ul.ana{margin:8px 0 10px;padding-left:20px;font-family:var(--serif);font-size:16.5px;line-height:1.55}
.ilgili ul.ana li{margin-bottom:8px}
.ilgili details.maddeler{margin:8px 0;font-size:14px}
.ilgili details.maddeler>summary{cursor:pointer;font-weight:600;color:var(--accent)}
.ilgili ol{padding-left:4px;list-style:none;margin:8px 0}
.ilgili ol li{margin-bottom:6px}.ilgili ol summary{cursor:pointer}
.ilgili ol p,.ilgili details.maddeler>p{color:var(--muted);margin:6px 0 10px 14px;line-height:1.55}
.ilgili .kaynak{font-size:12.5px;color:var(--muted);margin:10px 0 0}.ilgili .kaynak a{color:var(--accent)}
.ilgili-k{font-size:14px;margin:6px 0 10px}.ilgili-k ul{margin:4px 0 0;padding-left:18px}
.ilgili-k li{margin-bottom:4px}.ilgili-k a{color:var(--accent)}
"""


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


APP_HEAD = """<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#f7f5f1" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#151412" media="(prefers-color-scheme: dark)">
<link rel="icon" href="favicon-32.png" sizes="32x32"><link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Meclis">
<meta name="apple-mobile-web-app-status-bar-style" content="default">"""

APP_CSS = """
#cevrimdisi{position:sticky;top:0;z-index:20;background:var(--ham-bg);color:var(--ink);font-size:13px;
text-align:center;padding:6px 12px;border-bottom:1px solid var(--line)}
"""

# Uygulama katmanı: service worker kaydı, çevrimdışı bandı, yükleme düğmesi ve iOS ipucu
APP_JS = """
if('serviceWorker' in navigator&&location.protocol.startsWith('http'))navigator.serviceWorker.register('sw.js').catch(()=>{});
function cevrim(){let b=document.getElementById('cevrimdisi');
 if(!navigator.onLine){if(!b){b=document.createElement('div');b.id='cevrimdisi';
  b.textContent='Çevrimdışısınız — kaydedilmiş kopya gösteriliyor';document.body.prepend(b)}}else if(b)b.remove()}
addEventListener('online',cevrim);addEventListener('offline',cevrim);cevrim();
(()=>{let olay=null;const kur=document.getElementById('kur');
 addEventListener('beforeinstallprompt',e=>{e.preventDefault();olay=e;if(kur)kur.hidden=false});
 addEventListener('appinstalled',()=>{if(kur)kur.hidden=true});
 if(kur)kur.onclick=async()=>{if(!olay)return;olay.prompt();await olay.userChoice;olay=null;kur.hidden=true};
 const ip=document.getElementById('ios-ipucu');if(!ip)return;
 const kurulu=matchMedia('(display-mode: standalone)').matches||navigator.standalone;
 const ios=/iphone|ipad|ipod/i.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
 let gorulmus=false;try{gorulmus=!!localStorage.getItem('tbmm-ios-ipucu')}catch(e){}
 if(ios&&!kurulu&&!gorulmus)ip.hidden=false;
 ip.querySelector('button').onclick=()=>{ip.hidden=true;try{localStorage.setItem('tbmm-ios-ipucu','1')}catch(e){}}})();
"""


FIREBASE_KAYNAK = {
    "script": "https://www.gstatic.com/firebasejs/ https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/",
    "connect": ("https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://firestore.googleapis.com "
                "https://content-firebaseappcheck.googleapis.com https://www.google.com/recaptcha/"),
    "frame": "https://www.google.com/recaptcha/ https://recaptcha.google.com/recaptcha/ https://meclis-ce5d2.firebaseapp.com",
}


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
        "img-src 'self' data:",
        f"connect-src 'self' {dis['connect']}".strip(),
        f"frame-src {dis['frame'] or chr(39) + 'none' + chr(39)}",
        "worker-src 'self'", "manifest-src 'self'",
        "object-src 'none'", "base-uri 'none'", "form-action 'self'",
    ]
    return f'<meta http-equiv="Content-Security-Policy" content="{"; ".join(kurallar)}">'


def page(title: str, css: str, body: str, js: str, firebase: bool = False) -> str:
    html = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="strict-origin-when-cross-origin">
__CSP__<title>{escape(title)}</title>{APP_HEAD}<style>{CSS}{APP_CSS}{css}</style></head><body>{body}
<script>{READ_JS}{APP_JS}{js}</script></body></html>"""
    return html.replace("__CSP__", csp(html, firebase), 1)


MANIFEST = {
    "name": "Meclis Tutanakları",
    "short_name": "Meclis",
    "description": "TBMM Genel Kurul tutanakları ve açık oylama sonuçları",
    "lang": "tr",
    "id": "./",
    "start_url": "./",
    "scope": "./",
    "display": "standalone",
    "background_color": "#f7f5f1",
    "theme_color": "#f7f5f1",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}

# Sayfalar çevrimiçiyken her zaman güncel gelir (önce ağ); açılan sayfalar çevrimdışı okunmak üzere saklanır.
SW_JS = """
const SURUM='__SURUM__';
const KABUK='tbmm-kabuk-'+SURUM, SAYFALAR='tbmm-sayfalar', EN_FAZLA=80, ZAMAN_ASIMI=5000;
const KABUK_DOSYALARI=['./','index.html','manifest.webmanifest','icon-192.png','icon-512.png',
 'icon-maskable-512.png','apple-touch-icon.png','favicon-32.png'];

self.addEventListener('install',e=>{e.waitUntil(caches.open(KABUK).then(c=>c.addAll(KABUK_DOSYALARI)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(
 ks.filter(k=>k.startsWith('tbmm-kabuk-')&&k!==KABUK).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});

async function kirp(){const c=await caches.open(SAYFALAR);const ks=await c.keys();
 for(let i=0;i<ks.length-EN_FAZLA;i++)await c.delete(ks[i])}

async function sayfa(req,ad=SAYFALAR){
 const c=await caches.open(ad);
 // Önbellek anahtarında sorgu dizesi tutulmaz: giriş bağlantısındaki tek kullanımlık kod cihazda saklanmasın
 const u=new URL(req.url),anahtar=u.origin+u.pathname;
 const ag=fetch(req).then(async r=>{if(r.ok){await c.delete(anahtar);await c.put(anahtar,r.clone());if(ad===SAYFALAR)kirp()}return r});
 const kayitli=await c.match(anahtar)||await caches.match(req,{ignoreSearch:true});
 if(!kayitli){try{return await ag}catch(e){return cevrimdisiSayfa()}}
 // Ağ yavaşsa bekletmeden kaydedilmiş kopyayı göster
 return Promise.race([ag.catch(()=>kayitli),new Promise(r=>setTimeout(()=>r(kayitli),ZAMAN_ASIMI))]);
}

function cevrimdisiSayfa(){return new Response(`<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Çevrimdışı</title>
<body style="font:16px system-ui;padding:40px 20px;text-align:center;color:#6b665e;background:#f7f5f1">
<h1 style="font:28px Georgia,serif;color:#1d1b18">Çevrimdışısınız</h1>
<p>Bu sayfa daha önce açılmadığı için kaydedilmemiş.</p><p><a href="./" style="color:#a3122a">Ana sayfaya dön</a></p>`,
 {headers:{'Content-Type':'text/html; charset=utf-8'}})}

self.addEventListener('fetch',e=>{const r=e.request;const u=new URL(r.url);
 if(r.method!=='GET'||u.origin!==location.origin)return;
 if(r.mode==='navigate'||u.pathname.endsWith('.html')||u.pathname.endsWith('/'))e.respondWith(sayfa(r));
 else if(u.pathname.endsWith('.json'))e.respondWith(sayfa(r,'tbmm-veri'));
 else e.respondWith(caches.match(r,{ignoreSearch:true}).then(k=>k||fetch(r)));
});

// Bildirimler: gönderen taraf daha sonra eklenecek. Beklenen yük: {"title","body","url","tag"}
self.addEventListener('push',e=>{let d={};try{d=e.data?e.data.json():{}}catch(_){d={body:e.data&&e.data.text()}}
 e.waitUntil(self.registration.showNotification(d.title||'Meclis Tutanakları',{body:d.body||'',
  icon:'icon-192.png',badge:'favicon-32.png',tag:d.tag,data:{url:d.url||'./'}}))});
self.addEventListener('notificationclick',e=>{e.notification.close();
 const hedef=new URL(e.notification.data&&e.notification.data.url||'./',self.registration.scope).href;
 e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(ws=>{
  for(const w of ws)if(w.url===hedef&&'focus' in w)return w.focus();
  return self.clients.openWindow(hedef)}))});
"""


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
.hrow{display:flex;align-items:center;justify-content:space-between;gap:12px}
#kur{background:var(--accent);color:#fff;border-color:var(--accent);font-size:14px;white-space:nowrap}
.hbtn{display:flex;gap:8px;align-items:center}
.akislink{border:1px solid var(--line);background:var(--panel);border-radius:8px;padding:6px 12px;font-size:14px;
text-decoration:none;white-space:nowrap}.akislink:hover{border-color:var(--accent);color:var(--accent)}
#ios-ipucu{display:flex;gap:12px;align-items:center;background:var(--panel);border:1px solid var(--line);
border-radius:10px;padding:10px 14px;margin:0 0 16px;font-size:14px}
#ios-ipucu span{flex:1}
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
<header><div class="hrow"><h1>Meclis Tutanakları</h1><div class="hbtn"><button id="kur" hidden>Uygulamayı yükle</button>
<a class="akislink" href="akis.html">Akışım</a></div></div>
<p>TBMM Genel Kurul · {len(sessions)} tutanak · {len(votes)} açık oylama · son güncelleme {escape(updated)}</p></header>
<div id="ios-ipucu" hidden><span>Uygulama olarak kullanmak için Safari'de <b>Paylaş</b> düğmesine, sonra
<b>Ana Ekrana Ekle</b>'ye dokunun.</span><button>Tamam</button></div>
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
        pdf = guvenli_url(s["src"].get("pdf"))
        front = ('<p class="bos">Bu dönemin tutanağı TBMM tarafından yalnızca PDF olarak yayınlanmış. '
                 + (f'<a href="{escape(pdf)}" target="_blank" rel="noopener">PDF\'i aç ↗</a>' if pdf else "") + "</p>")

    ozet_html = "".join(f"<p>{escape(x)}</p>" for x in s["ozet"].split("\n") if x.strip()) \
        or '<p class="bos">Bu birleşim için özet yayınlanmamış.</p>'

    links = [f'<a href="{escape(s["tbmm_url"])}" target="_blank" rel="noopener">TBMM sayfası ↗</a>']
    for key, label in (("pdf", "PDF ↗"), ("docx", "Word ↗")):
        if guvenli_url(s["src"].get(key)):
            links.append(f'<a href="{escape(s["src"][key])}" target="_blank" rel="noopener">{label}</a>')

    karar_html = ""
    if s["decisions"]:
        karar_html = (f'<details class="box" open><summary>Bu birleşimde alınan kararlar ({len(s["decisions"])})'
                      '</summary><ul>' + "".join(f"<li>{escape(d)}</li>" for d in s["decisions"]) + "</ul></details>")
    oy_html = ""
    if s["votes"]:
        items = "".join(
            f'<div class="oyitem"><div class="oyh"><a href="{v["page"]}">{escape(v["baslik"])}</a> '
            f'<span class="pill {sonuc_cls(v["sonuc"])}">{escape(v["sonuc"] or "?")}</span></div>'
            f'{neyle_ilgili_html(v, compact=True)}{kirilim_html(v)}</div>'
            for v in s["votes"])
        oy_html = (f'<details class="box" open><summary>Açık oylamalar ({len(s["votes"])}) — '
                   f'partilere ve milletvekillerine göre kırılım</summary>{items}</details>')

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
.oyitem{padding:14px 0 6px;border-top:1px solid var(--line);margin-top:12px}
.oyitem:first-of-type{border-top:0;margin-top:4px}
.oyh{margin-bottom:6px;font-weight:600}
""" + KIRILIM_CSS + ILGILI_CSS
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
// Akıştan gelen bağlantı: #konusmaci=<id> ilgili milletvekilinin ilk konuşmasına götürür
{{const m=location.hash.match(/konusmaci=([\\w-]+)/);const b=m&&document.querySelector('.sp[data-s="'+m[1]+'"]');if(b)setTimeout(()=>b.click(),300)}}
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
""" + KIRILIM_JS
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

    links = []
    if guvenli_url(v.get("kaynak")):
        links.append(f'<a href="{escape(v["kaynak"])}" target="_blank" rel="noopener">TBMM oylama sayfası ↗</a>')
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
.ipucu{font-size:13px;margin:-4px 0 12px}
@media (max-width:640px){.barcell{display:none}.hide-sm{display:none}}
""" + KIRILIM_CSS + ILGILI_CSS
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
{neyle_ilgili_html(v)}
<h2>Oylama sonucu</h2>
<div class="stats">{resmi_html}</div>
<div class="bigbar">{bar(c, total)}<div class="legend">{''.join(f'<span><span class="dot {cls}"></span>{lbl} {c.get(code, 0)}</span>' for code, lbl, cls in OY_TURLERI)}</div></div>
<h2>Oyların parti kırılımı</h2>
<p class="muted ipucu">Bir parti dilimine tıklayınca o partiden o oyu veren milletvekilleri, oy türüne tıklayınca hepsi listelenir.</p>
{kirilim_html(v)}
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
""" + KIRILIM_JS
    return page(f"Oylama · {v['baslik'][:60]}", css, body, js)


# ---------- Ana akış ----------

def load_sira_sayilari() -> dict[tuple[int, str], dict]:
    out = {}
    for p in (DATA / "sira_sayilari").glob("donem*/*.json"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        out[(rec["donem"], rec["sira_sayisi"])] = rec
    return out


def collect() -> tuple[list[dict], list[dict]]:
    sessions, votes = [], []
    ss_all = load_sira_sayilari()
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
            **meta, "page": f"{base}.html", "doc": doc, "ozet": ozet, "has_text": txt.exists(), "txt": txt,
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
                    "ss": ss_all.get((meta["donem"], sira_no(v))),
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
    import akis  # akis arayuz'u içe aktarıyor; döngü olmasın diye burada
    written.update(akis.build(sessions, votes, OUT))
    for p in OUT.glob("*.html"):  # artık var olmayan eski sayfaları temizle
        if p.name not in written:
            p.unlink()
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    now = datetime.now(TR_TZ)
    # Uygulama dosyaları: ikonlar, manifest ve service worker (sürüm her derlemede değişir ki güncellemeler yayılsın)
    for icon in STATIC.glob("*.png"):
        shutil.copy2(icon, OUT / icon.name)
    (OUT / "manifest.webmanifest").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "sw.js").write_text(SW_JS.replace("__SURUM__", now.strftime("%Y%m%d%H%M%S")), encoding="utf-8")
    index = OUT / "index.html"
    index.write_text(build_index(sessions, votes, now.strftime("%d.%m.%Y %H:%M")), encoding="utf-8")
    return index


if __name__ == "__main__":
    print(build())
