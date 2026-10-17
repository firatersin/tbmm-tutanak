#!/usr/bin/env python3
"""data/ klasöründeki tutanak ve oylamalardan statik uygulamayı üretir (site/ klasörü).

  python arayuz.py        # siteyi yeniden üret

tbmm_tutanak.py her çalıştığında bunu otomatik çağırır. Bu dosya verileri hazırlar; sayfa şablonları
sayfalar.py'de, ortak iskelet ve bileşenler sablon.py'de, tasarım sistemi ve betikler web/ klasöründedir.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "site"
STATIC = ROOT / "static"
WEB = ROOT / "web"
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


def temiz_baslik(baslik: str) -> str:
    """'(S.Sayısı: 290) Millî Dayanışma ... Teklifi' -> 'Millî Dayanışma ... Teklifi' (sıra sayısı ayrı gösterilir)."""
    return re.sub(r"^\(S\.\s*Sayısı:\s*\d+\)\s*", "", baslik).strip()


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


def manset_karar(dec: list[str]) -> str:
    """Oturum başlığı için en anlamlı karar: liste devamı olan parçaları ("Görüşmelerinin ...") atlar,
    kanun teklifiyle ilgili kararı öne alır. Metin TBMM özetinden değiştirilmeden alınır."""
    tam = [d for d in dec if not re.match(r"^(Görüşme|Görüşül|İlişkin|ve |ile )", d)]
    for anahtar in ("Kanun Teklif", "Kanun Tasarı", "Tezkere", "önerisi"):
        for d in tam:
            if anahtar in d:
                return d
    return tam[0] if tam else (dec[-1] if dec else "")


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


# ---------- Oylamalar ----------

def vote_counts(v: dict) -> Counter:
    return Counter(oy_kodu(o[6]) for o in v["oylar"])


def party_table(v: dict, sira: list[str] | None = None) -> list[tuple[str, Counter]]:
    by: dict[str, Counter] = {}
    for o in v["oylar"]:
        by.setdefault(PARTI_KISA.get(o[3], o[3]), Counter())[oy_kodu(o[6])] += 1
    yer = {p: i for i, p in enumerate(sira or [])}
    return sorted(by.items(), key=lambda kv: (kv[0] == "Bağımsız", yer.get(kv[0], 99), -sum(kv[1].values())))


def sira_no(v: dict) -> str:
    no = re.sub(r"\D", "", v.get("sira_sayisi") or "")
    if not no:
        m = re.search(r"S\.\s*Sayısı\s*:\s*(\d+)", v.get("baslik", ""))
        no = m.group(1) if m else ""
    return no


# ---------- Toplama ----------

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
        dec = decisions(ozet)
        opening = next((ln.strip() for ln in ozet.split("\n") if ln.startswith("TBMM Genel Kurulu")), "")
        date = parse_date(meta["tarih"]) or datetime.min
        s = {
            **meta, "page": f"{base}.html", "doc": doc, "ozet": ozet, "has_text": txt.exists(), "txt": txt,
            "src": meta.get("kaynaklar", {}),
            "read_id": f"{meta['key']}:{durum_kodu(meta['durum'])}",
            "tbmm_url": f"https://www.tbmm.gov.tr/Tutanaklar/Tutanak?Id={meta['id']}",
            "date": date, "decisions": dec,
            "lead": short(manset_karar(dec)) if dec else opening,
            "minutes": max(1, round(doc["words"] / 220)),
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
                    "oturum": s,
                })
                s["votes"].append(v)
                votes.append(v)
        sessions.append(s)
    sessions.sort(key=lambda x: (x["date"], x["donem"], x["yil"], x["birlesim"]), reverse=True)
    return sessions, votes


# ---------- Uygulama dosyaları ----------

MANIFEST = {
    "name": "Meclis Tutanakları",
    "short_name": "Meclis",
    "description": "TBMM Genel Kurul tutanakları ve açık oylama sonuçları",
    "lang": "tr",
    "id": "./",
    "start_url": "./",
    "scope": "./",
    "display": "standalone",
    "background_color": "#F7F2E8",
    "theme_color": "#F7F2E8",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}

# Sayfalar ve veriler çevrimiçiyken her zaman güncel gelir (önce ağ); kabuk (biçem, betik, yazı tipi) önbellekten.
SW_JS = """
const SURUM='__SURUM__';
const KABUK='tbmm-kabuk-'+SURUM, SAYFALAR='tbmm-sayfalar', EN_FAZLA=80, ZAMAN_ASIMI=5000;
const KABUK_DOSYALARI=__KABUK__;

self.addEventListener('install',e=>{e.waitUntil(caches.open(KABUK).then(c=>c.addAll(KABUK_DOSYALARI)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(
 ks.filter(k=>k.startsWith('tbmm-kabuk-')&&k!==KABUK).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});

async function kirp(){const c=await caches.open(SAYFALAR);const ks=await c.keys();
 for(let i=0;i<ks.length-EN_FAZLA;i++)await c.delete(ks[i])}

async function onceAg(req,ad=SAYFALAR){
 const c=await caches.open(ad);
 // Önbellek anahtarında sorgu dizesi tutulmaz: giriş bağlantısındaki tek kullanımlık kod cihazda saklanmasın
 const u=new URL(req.url),anahtar=u.origin+u.pathname;
 const ag=fetch(req).then(async r=>{if(r.ok){await c.delete(anahtar);await c.put(anahtar,r.clone());if(ad===SAYFALAR)kirp()}return r});
 const kayitli=await c.match(anahtar)||await caches.match(req,{ignoreSearch:true});
 if(!kayitli){try{return await ag}catch(e){return cevrimdisi()}}
 return Promise.race([ag.catch(()=>kayitli),new Promise(r=>setTimeout(()=>r(kayitli),ZAMAN_ASIMI))]);
}

function cevrimdisi(){return new Response(`<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Çevrimdışı</title>
<body style="font:16px system-ui;padding:40px 20px;color:#57524A;background:#F7F2E8">
<h1 style="font:600 28px Georgia,serif;color:#1C1A17">Çevrimdışısınız</h1>
<p>Bu sayfa daha önce açılmadığı için kaydedilmemiş.</p><p><a href="./" style="color:#1E5260">Akışa dön</a></p>`,
 {headers:{'Content-Type':'text/html; charset=utf-8'}})}

self.addEventListener('fetch',e=>{const r=e.request;const u=new URL(r.url);
 if(r.method!=='GET'||u.origin!==location.origin)return;
 if(r.mode==='navigate'||u.pathname.endsWith('.html')||u.pathname.endsWith('/'))e.respondWith(onceAg(r));
 else if(u.pathname.endsWith('.json'))e.respondWith(onceAg(r,'tbmm-veri'));
 else e.respondWith(caches.match(r,{ignoreSearch:true}).then(k=>k||fetch(r)));
});

// Bildirimler: gönderen taraf daha sonra eklenecek. Beklenen yük: {"title","body","url","tag"}
self.addEventListener('push',e=>{let d={};try{d=e.data?e.data.json():{}}catch(_){d={body:e.data&&e.data.text()}}
 e.waitUntil(self.registration.showNotification(d.title||'Meclis Tutanakları',{body:d.body||'',lang:'tr',
  icon:'icon-192.png',badge:'favicon-32.png',tag:d.tag,data:{url:d.url||'./'}}))});
self.addEventListener('notificationclick',e=>{e.notification.close();
 const hedef=new URL(e.notification.data&&e.notification.data.url||'./',self.registration.scope).href;
 e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(ws=>{
  for(const w of ws)if(w.url===hedef&&'focus' in w)return w.focus();
  return self.clients.openWindow(hedef)}))});
"""


def build() -> Path:
    import akis
    import sablon as S
    import sayfalar as SY

    OUT.mkdir(exist_ok=True)
    sessions, votes = collect()
    ortak = akis.build_data(sessions, votes, OUT)
    ortak["konusmalar"] = akis.mp_konusmalari(sessions, ortak["index"])

    yazilan = SY.hepsini_yaz(sessions, votes, ortak, OUT)
    for p in OUT.glob("*.html"):  # artık var olmayan eski sayfaları temizle
        if p.name not in yazilan:
            p.unlink()

    # Tasarım sistemi, betikler, yazı tipleri, simgeler
    for alt in ("js", "fonts"):
        hedef = OUT / alt
        if hedef.exists():
            shutil.rmtree(hedef)
        shutil.copytree(WEB / alt, hedef)
    for f in ("stil.css", "fontlar.css"):
        shutil.copy2(WEB / f, OUT / f)
    (OUT / "partiler.css").write_text(S.parti_css(list(ortak["koltuk"])), encoding="utf-8")
    for icon in STATIC.glob("*.png"):
        shutil.copy2(icon, OUT / icon.name)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    (OUT / "manifest.webmanifest").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=1), encoding="utf-8")

    kabuk = (["./", "index.html", "oturumlar.html", "oylamalar.html", "ara.html", "takip.html", "hosgeldiniz.html",
              "manifest.webmanifest", "stil.css", "fontlar.css", "partiler.css",
              "icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png", "favicon-32.png",
              "fonts/newsreader-normal-latin.woff2", "fonts/newsreader-normal-latin-ext.woff2",
              "fonts/ibm-plex-sans-normal-latin.woff2", "fonts/ibm-plex-sans-normal-latin-ext.woff2"]
             + [f"js/{p.name}" for p in (WEB / "js").glob("*.js") if p.name != "hesap.js"])
    (OUT / "sw.js").write_text(SW_JS.replace("__SURUM__", ortak["surum"]).replace("__KABUK__", json.dumps(kabuk)),
                               encoding="utf-8")
    return OUT / "index.html"


if __name__ == "__main__":
    print(build())
