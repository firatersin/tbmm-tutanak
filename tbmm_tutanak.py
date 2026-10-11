#!/usr/bin/env python3
"""TBMM Genel Kurul tutanaklarını ve açık oylama sonuçlarını tarar, yenilerini kaydeder.

Yalnızca standart kütüphane kullanır.

  python tbmm_tutanak.py                       # günlük çalışma: yeni birleşimler + durum değişiklikleri
  python tbmm_tutanak.py --donem 28 --yil 4    # belirli bir yasama yılını (geriye dönük) indir
  python tbmm_tutanak.py --dry-run             # hiçbir şey kaydetmeden neyin yeni olduğunu göster
  python tbmm_tutanak.py --orijinaller         # PDF/DOCX/HTML orijinallerini de orijinal/ klasörüne indir

Her birleşim data/donemNN/yilN/birlesimNNN/ altında saklanır:
  meta.json     kimlik, tarih, durum ve TBMM'deki orijinal dosyaların adresleri
  tutanak.txt   tutanak metni (Ham ya da Tam/Basılmış HTML'den)
  ozet.txt      tutanak özeti
  oylama.json   açık oylama sonuçları (milletvekili bazında)

Takip mantığı: durum (Ham -> Tam -> Basılmış) ya da kaynak adresleri değişirse birleşim yeniden işlenir.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://www.tbmm.gov.tr"
UA = "Mozilla/5.0 (tbmm-tutanak-arsiv; kisisel kullanim)"
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ORIG = ROOT / "orijinal"
STATE_FILE = ROOT / "state.json"
DELAY = 1.0  # istekler arası bekleme (sn)
TR_TZ = timezone(timedelta(hours=3))

log = logging.getLogger("tbmm")


# ---------- HTTP ----------

def get(url: str, retries: int = 3) -> bytes:
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            time.sleep(DELAY)
            return data
        except Exception as e:
            if attempt == retries:
                raise
            log.warning("Hata (%s), tekrar deneniyor %d/%d: %s", e, attempt, retries, url)
            time.sleep(5 * attempt)
    raise RuntimeError("unreachable")


def decode(raw: bytes) -> str:
    """TBMM sayfaları bazen UTF-8, bazen windows-1254; beyan edilen charset'e her zaman güvenilmiyor."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("windows-1254", errors="replace")


def get_text(url: str) -> str:
    return decode(get(url))


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).replace("\xa0", " ").strip()


def durum_kodu(durum: str) -> str:
    d = durum.lower()
    return "basilmis" if d.startswith("bas") else "tam" if d.startswith("tam") else "ham"


# ---------- Liste ve detay sayfaları ----------

def list_years() -> list[tuple[int, int]]:
    """Sitede listelenen tüm (dönem, yasama yılı) çiftleri, en yeniden eskiye."""
    t = get_text(f"{BASE}/Tutanaklar/TutanakMetinleri")
    pairs = {(int(d), int(y)) for d, y in
             re.findall(r"DoneminTutanakMetinleri\?Donem=(\d+)&(?:amp;)?YasamaYili=(\d+)", t)}
    return sorted(pairs, reverse=True)


def list_sessions(donem: int, yil: int) -> list[dict]:
    """Bir yasama yılındaki birleşimler (özet ve açık oylama bağlantılarıyla)."""
    t = get_text(f"{BASE}/Tutanaklar/DoneminTutanakMetinleri?Donem={donem}&YasamaYili={yil}")
    out, seen = [], set()
    for row in re.findall(r"<tr>(.*?)</tr>", t, re.S):
        m = re.search(r"Tutanak\?Id=([0-9a-f-]{36})", row)
        if not m:
            continue
        cells = [clean(c) for c in re.findall(r"<td>(.*?)</td>", row, re.S)]
        bm = re.match(r"(\d+)", cells[0]) if cells else None
        if not bm:
            continue
        birlesim = int(bm.group(1))
        key = f"{donem}-{yil}-{birlesim}"
        if key in seen:  # sitede aynı satır bazen iki kez listeleniyor
            continue
        seen.add(key)
        ozet, oylama = None, []
        # Eski dönemlerde URL dosya türünü söylemiyor; bağlantı metnine bakmak gerekiyor
        for url, label in re.findall(r"<a[^>]*href=['\"](https://cdn\.tbmm\.gov\.tr/[^'\"]+)['\"][^>]*>(.*?)</a>", row, re.S):
            label = clean(label).lower()
            if "oylama" in label:
                oylama.append(url)
            elif "özet" in label:
                ozet = url
        out.append({
            "key": key, "donem": donem, "yil": yil, "birlesim": birlesim,
            "id": m.group(1),
            "tarih": cells[1] if len(cells) > 1 else "",
            "durum": cells[2] if len(cells) > 2 else "",
            "ozet_url": ozet, "oylama_urls": oylama,
        })
    return out


def detail_files(tutanak_id: str) -> list[str]:
    """Tutanak detay sayfasındaki CDN dosyaları (html/docx/pdf)."""
    t = get_text(f"{BASE}/Tutanaklar/Tutanak?Id={tutanak_id}")
    urls = re.findall(r"https://cdn\.tbmm\.gov\.tr/TbmmWeb/Tutanak[^\"'#\s]+", t)
    return sorted({html.unescape(u) for u in urls})


def pick_sources(files: list[str]) -> dict:
    """Detay sayfası dosyalarından okunacak metni ve indirilebilir orijinalleri seç."""
    def find(kind: str, ext: str):
        return next((u for u in files if f"/{kind}/" in u and u.lower().endswith(ext)), None)
    return {
        "metin_html": find("Tam", ".html") or find("Ham", ".html"),
        "pdf": find("Basilmis", ".pdf") or find("Tam", ".pdf") or find("Ham", ".pdf"),
        "docx": find("Tam", ".docx") or find("Ham", ".docx"),
    }


# ---------- Metin çıkarma ----------

class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "title"):
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "title"):
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: bytes | str) -> str:
    p = _TextExtractor()
    p.feed(decode(raw) if isinstance(raw, bytes) else raw)
    text = "".join(p.parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


# ---------- Açık oylama ayrıştırma ----------

SAYI_ALANLARI = {
    "üye sayısı": "uye", "kabul edenler": "kabul", "reddedenler": "ret", "çekimserler": "cekimser",
    "boş oylar": "bos", "geçersiz oylar": "gecersiz", "mükerrer oylar": "mukerrer",
    "toplam": "toplam", "açık üyelikler": "acik",
}


def parse_oylama(page: str) -> list[dict]:
    """Bir Açık Oylama Sonuçları sayfasındaki tüm oylamalar.

    Sayfa yapısı: <h2>Kabul Edilenler</h2> <button class="accordion">başlık</button>
    <div class="panel"> <table id="oySonuc">toplamlar</table> ... <table id="tblTbmmOylama">oylar</table>
    """
    votes = []
    # Bölüm başlıklarıyla (Kabul Edilenler / Kabul Edilmeyenler ...) birlikte böl
    parts = re.split(r"(<h2[^>]*>.*?</h2>|<button[^>]*class=\"accordion\"[^>]*>.*?</button>)", page, flags=re.S)
    bolum, baslik = "", ""
    for part in parts:
        if part.startswith("<h2"):
            bolum = clean(part)
            continue
        if part.startswith("<button"):
            baslik = re.sub(r"^\d+\.\s*", "", clean(part))
            continue
        if not baslik or 'id="tblTbmmOylama"' not in part:  # sayfa başındaki CSS de bu adı içeriyor
            continue
        sayilar = {}
        sm = re.search(r'id="oySonuc".*?</table>', part, re.S)
        for k, v in re.findall(r"<tr>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>", sm.group(0) if sm else "", re.S):
            alan = SAYI_ALANLARI.get(clean(k).lower())
            num = re.search(r"\d+", clean(v))
            if alan and num:
                sayilar[alan] = int(num.group(0))
        rest = part[sm.end():] if sm else part
        tm = re.search(r'id="tblTbmmOylama"', rest)
        # Sıra sayısı ve sonuç ("Kabul Edilmiştir") toplamlar tablosunun son satırında
        ozet_alani = clean((sm.group(0) if sm else "") + " " + (rest[: tm.start()] if tm else ""))
        # "Kabul Edilmiştir", "Kabul Edilmemiştir", "Kanunlaşmıştır" ...
        rm = re.search(r"((?:[A-ZÇĞİÖŞÜ]\w* )?[A-ZÇĞİÖŞÜ]\w*(?:miştir|mıştır|muştur|müştür))", ozet_alani)
        sonuc = rm.group(1) if rm else ""
        ss = re.search(r"Sıra Sayısı\s*:\s*([\d/ ]+)", ozet_alani)
        tbody = rest[tm.end():] if tm else ""
        tbody = tbody[tbody.find("<tbody"):] if "<tbody" in tbody else tbody
        oylar = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody, re.S):
            cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            if len(cells) >= 9:
                # il, soyad, ad, parti, sistem, pusula, sonuç, tarih, saat
                cells[4] = re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰]+$", "", cells[4])
                cells[6] = re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰]+$", "", cells[6])
                oylar.append(cells[:9])
        saatler = sorted(f"{o[7]} {o[8]}" for o in oylar if re.match(r"\d", o[7]))
        votes.append({
            "no": len(votes) + 1,
            "baslik": baslik,
            "bolum": bolum,
            "sonuc": sonuc,
            "sira_sayisi": ss.group(1).strip() if ss else "",
            "sayilar": sayilar,
            "baslangic": iso_dt(saatler[0]) if saatler else "",
            "oylar": oylar,
        })
    return votes


# ---------- Sıra sayısı (komisyon raporu) ve gerekçeler ----------

SS_DIR = DATA / "sira_sayilari"
_ortak_donem: dict[int, str] = {}


def ortak_donem_id(donem: int) -> str | None:
    """Komisyon raporu sorgusunda dönemi temsil eden kimlik (sorgu formundaki seçeneklerden)."""
    if not _ortak_donem:
        t = get_text(f"{BASE}/yasama/komisyon-raporlari")
        sel = re.search(r'name="OrtakDonemId".*?</select>', t, re.S)
        for val, num in re.findall(r'<option value="([^"]+)">\s*(\d+)\s*</option>', sel.group(0) if sel else ""):
            _ortak_donem[int(num)] = val.lower()
    return _ortak_donem.get(donem)


def find_sira_sayisi(donem: int, no: str) -> dict | None:
    """Sıra sayısının komisyon raporu PDF'i, başlığı ve dağıtım tarihi."""
    oid = ortak_donem_id(donem)
    if not oid:
        return None
    q = urllib.parse.urlencode({"OrtakDonemId": oid, "SiraSayisiNumarasi": no, "draw": 1, "start": 0, "length": 10})
    data = json.loads(get_text(f"{BASE}/Yasama/KomisyonRaporlari-Sonuc-Sayfa?{q}"))
    for row in data.get("data", []):
        m = re.search(r'href="([^"]+\.pdf)"[^>]*>\s*(\d+)\s*<', row.get("siraSayisi", ""))
        if m and m.group(2) == str(no) and not row.get("siraSayiEki"):
            baslik = clean(row.get("baslik", ""))
            sonuc = re.search(r"Sonucu\s*:\s*([^:]+?)(?:\s+Kanun No\s*:|$)", baslik)
            kanun = re.search(r"Kanun No\s*:\s*(\d+)", baslik)
            return {"pdf": m.group(1), "dagitim": row.get("dagitimTarihi", ""),
                    "baslik": re.split(r"\s+Sonucu\s*:", baslik)[0],
                    "durum": sonuc.group(1).strip() if sonuc else "",
                    "kanun_no": kanun.group(1) if kanun else ""}
    return None


MADDE_RE = re.compile(r"\n\s*((?:Geçici )?Madde \d+)\s*[-–‒]\s*")
SENT_END = re.compile(r"(?<=[a-zçğıöşüâîû\)’'])\.(?=\s+[A-ZÇĞİÖŞÜ\"“(]|\s*$)")
RUTIN_RE = re.compile(r"(tanımlar|Yürürlük maddesidir|Yürütme maddesidir|yürürlük tarihi|yürütme maddesi)", re.I)


GEREKCE_RE = re.compile(r"\n\s*(?:GENEL )?GEREKÇE\s*\n")
KANUN_METNI_RE = re.compile(r"\nMADDE 1\s*[-–‒]")
SAYFA_BASLIGI_RE = re.compile(r"\n?\s*‒\s*\d+\s*‒\s*\n\s*Türkiye Büyük Millet Meclisi\s+\(Sıra Sayısı:[^)]*\)")
MAX_PDF = 100 * 1024 * 1024  # bütçe/kesin hesap raporları 150 MB'ı aşabiliyor; onları atla
SUNUS_RE = re.compile(r"\n\s*T\.\s?C\.\s*(?:\n\s*)?Cumhurbaşkanlığı|\n\s*TÜRKİYE BÜYÜK MİLLET MECLİSİ BAŞKANLIĞINA")
AMAC_RE = re.compile(r"(amaçlan|hedeflen|öngörül|Anlaşma ile|Anlaşmayla|Teklif ile|Teklifle|düzenleme yapılmaktadır)")
TR_HARFLER = "abcçdefgğhıijklmnoöprsştuüvyz"


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _first_sentence(s: str) -> str:
    first = SENT_END.split(s, maxsplit=1)[0].strip()
    return first if first.endswith(".") else first + "."


def _numbered_list(raw: str) -> list[str]:
    """Genel gerekçedeki '1. ... 2. ...' biçimli resmi listeyi (ör. anlaşmanın temel esasları) aynen çıkarır."""
    starts = [(int(m.group(1)), m.start(), m.end()) for m in re.finditer(r"\n\s*(\d{1,2})[.)]\s+", raw)]
    run = []
    for num, s, e in starts:
        if num == len(run) + 1:
            run.append((s, e))
        elif num == 1 and len(run) < 2:  # daha uzun bir liste yeniden başlıyorsa onu al
            run = [(s, e)]
    if len(run) < 2:
        return []
    items = []
    for i, (s, e) in enumerate(run):
        body = raw[e: run[i + 1][0]] if i + 1 < len(run) else raw[e:]
        if i + 1 == len(run):  # son madde: noktalama + satır sonu + yeni cümleyle başlayan satırda dur
            stop = re.search(r"[.;,]\s*\n(?=[A-ZÇĞİÖŞÜ][a-zçğıöşü’']+\s)", body)
            body = body[: stop.start() + 1] if stop else body
        items.append(_flat(body).rstrip(",;"))
    return [x for x in items if 10 < len(x) < 1200]


def _lettered_list(genel: str) -> list[str]:
    """Metin içi 'a) ... b) ... c) ...' listesini (ör. 'Anlaşma ile; a) ..., b) ...') aynen çıkarır."""
    marks = [(m.group(1), m.start(), m.end())
             for m in re.finditer(rf"(?:^|[\s;:,(])([{TR_HARFLER}])\)\s+", genel)]
    run = []
    for letter, s, e in marks:
        if letter == TR_HARFLER[len(run)]:
            run.append((s, e))
        elif letter == "a" and len(run) < 2:
            run = [(s, e)]
    if len(run) < 2:
        return []
    items = []
    for i, (s, e) in enumerate(run):
        body = genel[e: run[i + 1][0]] if i + 1 < len(run) else genel[e:]
        if i + 1 == len(run):
            body = _first_sentence(body)
        items.append(re.sub(r"\s+(ile|ve)$", "", body.strip().rstrip(",;")))
    return [x for x in items if 5 < len(x) < 800]


def parse_gerekce(pdf_bytes: bytes) -> dict:
    """Komisyon raporu PDF'inden genel gerekçe ve madde gerekçeleri (resmi metin, değiştirilmeden)."""
    import io
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = ""
    # Gerekçeler belgenin başında; tüm PDF'i (yüzlerce sayfa olabiliyor) okumamak için kanun metnine gelince dur
    for i, page in enumerate(reader.pages):
        text += "\n" + (page.extract_text() or "")
        g = GEREKCE_RE.search(text)
        if (g and KANUN_METNI_RE.search(text, g.end())) or i > 150:
            break
    text = SAYFA_BASLIGI_RE.sub("", text)
    g = GEREKCE_RE.search(text)
    if not g:
        return {"genel_gerekce": "", "esaslar": [], "amac": [], "maddeler": []}
    end = KANUN_METNI_RE.search(text, g.end())
    body = text[g.end(): end.start() if end else len(text)]
    # Kanun metninden önceki başlık satırlarını (ör. "... KANUN TEKLİFİ") ve komisyon raporu başlığını kes
    body = re.split(r"\n[A-ZÇĞİÖŞÜ ,'’\-]{25,}\n", body)[0]
    body = re.split(r"\n[^\n]{0,80}Komisyonu Raporu\s*\n", body)[0]

    mg = body.find("MADDE GEREKÇELERİ")
    genel_raw = body[:mg] if mg >= 0 else body
    genel_raw = SUNUS_RE.split(genel_raw)[0]  # ardından gelen Cumhurbaşkanlığı sunuş yazısını kes
    maddeler = []
    if mg >= 0:
        parts = MADDE_RE.split("\n" + body[mg + len("MADDE GEREKÇELERİ"):])
        for label, mb in zip(parts[1::2], parts[2::2]):
            mb = _flat(mb)
            first = _first_sentence(mb)
            maddeler.append({"no": label.replace("Madde ", ""), "ilk": first, "metin": mb,
                             "rutin": bool(RUTIN_RE.search(first)) and len(first) < 120})
    genel = _flat(genel_raw)
    sentences = [s.strip() + "." for s in SENT_END.split(genel) if s.strip()]
    # Liste yoksa: genel gerekçede amacı bildiren cümleler (aynen), o da yoksa ilk iki cümle
    amac = [s for s in sentences if AMAC_RE.search(s) and len(s) < 700][:5] or sentences[:2]
    return {
        "genel_gerekce": genel,
        "esaslar": _numbered_list(genel_raw) or _lettered_list(genel),
        "amac": amac,
        "maddeler": maddeler,
    }


def remote_size(url: str) -> int | None:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            n = r.headers.get("Content-Length")
        return int(n) if n else None
    except Exception:
        return None


def ss_path(donem: int, no: str) -> Path:
    return SS_DIR / f"donem{donem}" / f"{no}.json"


def ensure_sira_sayilari() -> int:
    """Oylamalarda geçen ve henüz işlenmemiş sıra sayılarını indirip gerekçelerini çıkarır."""
    needed = set()
    for p in DATA.glob("donem*/yil*/birlesim*/oylama.json"):
        donem = int(p.parts[-4].replace("donem", ""))
        for v in json.loads(p.read_text(encoding="utf-8")):
            no = re.sub(r"\D", "", v.get("sira_sayisi") or "")
            if not no:
                m = re.search(r"S\.\s*Sayısı\s*:\s*(\d+)", v.get("baslik", ""))
                no = m.group(1) if m else ""
            if no:
                needed.add((donem, no))
    done = 0
    for donem, no in sorted(needed):
        path = ss_path(donem, no)
        if path.exists():
            continue
        try:
            info = find_sira_sayisi(donem, no)
            rec = {"donem": donem, "sira_sayisi": no, "bulunamadi": info is None}
            if info:
                rec.update(info)
                size = remote_size(info["pdf"])
                if size and size > MAX_PDF:
                    rec["buyuk_pdf_mb"] = round(size / 1024 / 1024)
                else:
                    rec.update(parse_gerekce(get(info["pdf"])))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            if not info:
                ozet = "bulunamadı"
            elif "buyuk_pdf_mb" in rec:
                ozet = f"PDF çok büyük ({rec['buyuk_pdf_mb']} MB), gerekçe çıkarılmadı"
            else:
                ozet = (f"{len(rec['maddeler'])} madde gerekçesi, {len(rec['esaslar'])} esas, "
                        f"genel gerekçe {len(rec['genel_gerekce'])} karakter")
            log.info("Sıra sayısı %d/%s: %s", donem, no, ozet)
            done += 1
        except Exception as e:
            log.error("Sıra sayısı %d/%s işlenemedi: %s", donem, no, e)
    return done


def iso_dt(s: str) -> str:
    """'10.08.2026 16:45:41' -> '2026-08-10T16:45:41'"""
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4}) (\d{1,2}:\d{2}:\d{2})", s)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}T{m.group(4)}" if m else ""


# ---------- Kaydetme ----------

def session_folder(s: dict) -> Path:
    return DATA / f"donem{s['donem']}" / f"yil{s['yil']}" / f"birlesim{s['birlesim']:03d}"


def process_session(s: dict, files: list[str], keep_originals: bool) -> Path:
    folder = session_folder(s)
    folder.mkdir(parents=True, exist_ok=True)
    src = pick_sources(files)

    if src["metin_html"]:
        raw = get(src["metin_html"])
        (folder / "tutanak.txt").write_text(html_to_text(raw), encoding="utf-8")
    if s["ozet_url"]:
        (folder / "ozet.txt").write_text(html_to_text(get(s["ozet_url"])), encoding="utf-8")

    votes = []
    for url in s["oylama_urls"]:
        for v in parse_oylama(get_text(url)):
            v["no"] = len(votes) + 1
            v["kaynak"] = url
            votes.append(v)
    oy_path = folder / "oylama.json"
    if votes:
        oy_path.write_text(json.dumps(votes, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    elif oy_path.exists():
        oy_path.unlink()

    if keep_originals:
        odir = ORIG / folder.relative_to(DATA)
        odir.mkdir(parents=True, exist_ok=True)
        for url in files:
            (odir / f"{url.split('/')[-2]}{Path(url).suffix.lower()}").write_bytes(get(url))

    meta = {
        **{k: s[k] for k in ("key", "donem", "yil", "birlesim", "id", "tarih", "durum")},
        "kaynaklar": {**src, "ozet": s["ozet_url"], "oylama": s["oylama_urls"], "tumu": files},
        "oylama_sayisi": len(votes),
        "indirildi": datetime.now(TR_TZ).isoformat(timespec="seconds"),
    }
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder


# ---------- Durum ----------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_FILE)


def fingerprint(s: dict) -> dict:
    return {k: s[k] for k in ("donem", "yil", "id", "durum", "ozet_url", "oylama_urls")}


# ---------- Ana akış ----------

def years_to_scan(state: dict, args) -> list[tuple[int, int]]:
    if args.donem and args.yil:
        return [(args.donem, args.yil)]
    latest = list_years()[0]
    years = {latest}
    # Önceki yıllarda henüz Basılmış olmayan tutanaklar varsa, durum geçişini yakalamak için onları da tara
    for v in state.values():
        if durum_kodu(v["durum"]) != "basilmis":
            years.add((v["donem"], v["yil"]))
    return sorted(years, reverse=True)


def run(args) -> int:
    state = load_state()
    changed = errors = 0
    for donem, yil in years_to_scan(state, args):
        sessions = list_sessions(donem, yil)
        log.info("%d. Dönem %d. Yasama Yılı: %d birleşim listelendi", donem, yil, len(sessions))
        for s in sorted(sessions, key=lambda x: x["birlesim"]):
            old = state.get(s["key"])
            fp = fingerprint(s)
            if old and {k: old.get(k) for k in fp} == fp and not args.yeniden:
                continue  # listede değişiklik yok
            try:
                files = detail_files(s["id"])
                reason = "YENİ" if not old else f"GÜNCELLENDİ ({old['durum']} -> {s['durum']})"
                log.info("%s: %s %d. Birleşim, %s [%s], %d oylama sayfası",
                         reason, f"{donem}/{yil}", s["birlesim"], s["tarih"], s["durum"], len(s["oylama_urls"]))
                if args.dry_run:
                    continue
                process_session(s, files, args.orijinaller)
                state[s["key"]] = {**fp, "tarih": s["tarih"], "dosyalar": files}
                save_state(state)
                changed += 1
            except Exception as e:
                errors += 1
                log.exception("%s işlenemedi: %s", s["key"], e)
    if not args.dry_run:
        n = ensure_sira_sayilari()
        if n:
            log.info("%d sıra sayısı (komisyon raporu gerekçesi) işlendi", n)
    log.info("Bitti: %d birleşim kaydedildi/güncellendi, %d hata", changed, errors)
    if not args.dry_run and not args.arayuzsuz:
        try:
            import arayuz
            log.info("Arayüz güncellendi: %s", arayuz.build())
        except Exception as e:
            errors += 1
            log.exception("Arayüz üretilemedi: %s", e)
    return 1 if errors else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--donem", type=int, help="Belirli dönem (ör. 28)")
    ap.add_argument("--yil", type=int, help="Belirli yasama yılı (ör. 4)")
    ap.add_argument("--dry-run", action="store_true", help="Kaydetmeden sadece raporla")
    ap.add_argument("--yeniden", action="store_true", help="Değişmemiş olsa bile yeniden işle")
    ap.add_argument("--orijinaller", action="store_true", help="PDF/DOCX/HTML orijinallerini de indir")
    ap.add_argument("--arayuzsuz", action="store_true", help="Sonunda arayüzü üretme")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    (ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(ROOT / "logs" / "tbmm.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
