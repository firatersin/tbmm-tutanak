"""Sayfa şablonları. Her sayfa sablon.sayfa() iskeletiyle üretilir; etkileşim web/js/ altındaki modüllerde."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

import akis
import arayuz as A
import sablon as S

DONEM_YIL = "{donem}. Dönem · {yil}. Yasama Yılı"


# ---------- Ortak parçalar ----------

def durum_etiketi(durum: str) -> str:
    k = A.durum_kodu(durum)
    if k == "ham":
        return '<span class="etiket ham" title="Stenograflarca deşifre edilmiş, uzman incelemesinden geçmemiş">Ham tutanak</span>'
    return f'<span class="etiket kesin">{"Basılmış" if k == "basilmis" else "Tam tutanak"}</span>'


def sonuc_turu(sonuc: str) -> str:
    s = sonuc.lower()
    return "ret" if ("edilme" in s or "redd" in s) else "kabul" if s else ""


def saat(v: dict) -> str:
    return v["baslangic"][11:16].replace(":", ".") if v.get("baslangic") else ""


def kisa_tarih(d: datetime) -> str:
    return f"{d.day} {A.AYLAR[d.month - 1]} {d.year}"


def ay_basligi(d: datetime) -> str:
    return f"{A.AYLAR[d.month - 1]} {d.year}"


def bos(baslik: str, metin: str, dugme: str = "") -> str:
    return f'<div class="bos"><h2>{escape(baslik)}</h2><p>{metin}</p>{dugme}</div>'


def oylama_satiri(v: dict, *, oturum_goster: bool = True, ek: str = "", sayim_veri=None) -> str:
    sayilar = sayim_veri if sayim_veri is not None else A.vote_counts(v)
    bilgi = [f'<span class="tur">Oylama</span>']
    if oturum_goster:
        bilgi.append(f"<span>{v['birlesim']}. Birleşim · {kisa_tarih(v['date'])}{' · ' + saat(v) if saat(v) else ''}</span>")
    elif saat(v):
        bilgi.append(f"<span>{saat(v)}</span>")
    q = escape(f"{v['baslik']} {v['sonuc']} {v['tarih_yazi']} {v['birlesim']}. birleşim")
    return (f'<li class="satir" data-q="{q}" data-f="{sonuc_turu(v["sonuc"])}" data-id="{escape(v["read_id"])}">'
            f'<a href="{v["page"]}"><div class="bilgi">{"".join(bilgi)}</div><h3>{escape(A.temiz_baslik(v["baslik"]))}</h3>'
            f'<p class="govde" style="-webkit-line-clamp:1">{escape(v["sonuc"] or "Sonuç belirtilmemiş")}</p>'
            f'{S.sayim(sayilar, sinif="ince")}{ek}</a></li>')


def ay_gruplari(ogeler: list, tarih, satir) -> str:
    gruplar: dict[str, list] = {}
    for o in ogeler:
        gruplar.setdefault(ay_basligi(tarih(o)), []).append(satir(o))
    return "".join(f'<section data-grup><h2 class="gun">{escape(ay)}</h2><ul class="liste">{"".join(s)}</ul></section>'
                   for ay, s in gruplar.items())


# ---------- Akış ----------

def akis_sayfasi() -> str:
    govde = """<div class="kap">
<div class="baslik"><h1>Akış</h1><p class="alt" id="alt">&nbsp;</p></div>
<div class="on-izleme" id="yukle" hidden><p class="not"></p>
  <div style="display:flex;gap:8px;margin-top:10px"><button class="dugme" id="yukle-dugme" hidden>Uygulamayı yükle</button>
  <button class="dugme yalin" id="yukle-kapat">Kapat</button></div></div>
<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin:10px 0 5px">
  <div class="cipler" id="tur" role="group" aria-label="Kayıt türü">
    <button class="cip" data-v="" aria-pressed="true">Tümü</button>
    <button class="cip" data-v="O" aria-pressed="false">Oylamalar</button>
    <button class="cip" data-v="T" aria-pressed="false">Tutanaklar</button></div>
  <label class="kutu" style="font-size:14.5px;align-items:center"><input type="checkbox" id="sadeceYeni">Yalnızca okunmamışlar</label>
</div>
<div id="liste" aria-live="polite"><p class="not" style="padding:30px 0">Kayıtlar yükleniyor…</p></div>
<button class="dugme daha" id="daha" hidden></button>
<noscript><p class="bos">Kişisel akış için JavaScript gerekir. <a href="oturumlar.html">Oturumlar</a> ve <a href="oylamalar.html">Oylamalar</a> sekmeleri JavaScript olmadan da çalışır.</p></noscript>
</div>"""
    return S.sayfa("Meclis Tutanakları", govde, sekme="akis", modul="akis.js",
                   aciklama="TBMM Genel Kurul tutanakları ve açık oylama sonuçları, takip ettiklerinize göre.")


# ---------- Oturumlar ----------

def oturumlar_sayfasi(sessions: list[dict]) -> str:
    son = sessions[0]["date"] if sessions else None
    tatil = ""
    if son and datetime.now() - son > timedelta(days=12):
        tatil = f'<p class="not" style="margin-top:6px">Genel Kurul son olarak {escape(A.tarih_yazi(son))} günü toplandı.</p>'

    def satir(s):
        q = escape(f"{s['birlesim']}. birleşim {A.tarih_yazi(s['date'])} {s['lead']}")
        f = ["oylamali"] if s["votes"] else []
        f.append("ham" if A.durum_kodu(s["durum"]) == "ham" else "kesin")
        sayilar = f"{len(s['doc']['speakers'])} konuşmacı" + (f" · {len(s['votes'])} açık oylama" if s["votes"] else "")
        return (f'<li class="satir" data-q="{q}" data-f="{" ".join(f)}" data-id="{escape(s["read_id"])}"><a href="{s["page"]}">'
                f'<div class="bilgi"><span class="tur">{s["birlesim"]}. Birleşim</span>{durum_etiketi(s["durum"])}</div>'
                f'<h3>{escape(A.tarih_yazi(s["date"]))}</h3>'
                + (f'<p class="govde" style="-webkit-line-clamp:2">{escape(s["lead"])}</p>' if s["lead"] else "")
                + f'<div class="bilgi" style="margin-top:6px">{sayilar}</div></a></li>')

    govde = f"""<div class="kap">
<div class="baslik"><h1>Oturumlar</h1><p class="alt">Genel Kurul birleşimleri, en yenisi üstte · {len(sessions)} oturum</p>{tatil}</div>
<div class="cipler" id="filtre" role="group" aria-label="Süzgeç">
  <button class="cip" data-v="" aria-pressed="true">Tümü</button><button class="cip" data-v="oylamali" aria-pressed="false">Açık oylama olanlar</button>
  <button class="cip" data-v="ham" aria-pressed="false">Ham tutanak</button><button class="cip" data-v="kesin" aria-pressed="false">Kesinleşmiş</button></div>
<div style="margin-top:10px"><label class="gizli-metin" for="suz">Oturumlarda süz</label>
<input class="alan" id="suz" type="search" placeholder="Tarih, birleşim no ya da karar" autocomplete="off"></div>
<p class="not" id="sayac" style="margin-top:8px" aria-live="polite"></p>
{ay_gruplari(sessions, lambda s: s["date"], satir) or bos("Henüz oturum yok", "İlk tutanak yayımlandığında burada görünecek.")}
</div>"""
    return S.sayfa("Oturumlar · Meclis Tutanakları", govde, sekme="oturumlar", modul="liste.js")


# ---------- Oylamalar ----------

def oylamalar_sayfasi(votes: list[dict]) -> str:
    sirali = sorted(votes, key=lambda v: (v["date"], v["baslangic"] or ""), reverse=True)
    govde = f"""<div class="kap">
<div class="baslik"><h1>Oylamalar</h1><p class="alt">Açık oylamalar: her milletvekilinin oyu kayıtlıdır · {len(votes)} oylama</p></div>
<div class="cipler" id="filtre" role="group" aria-label="Sonuca göre">
  <button class="cip" data-v="" aria-pressed="true">Tümü</button><button class="cip" data-v="kabul" aria-pressed="false">Kabul edilenler</button>
  <button class="cip" data-v="ret" aria-pressed="false">Kabul edilmeyenler</button></div>
<div style="margin-top:10px"><label class="gizli-metin" for="suz">Oylamalarda süz</label>
<input class="alan" id="suz" type="search" placeholder="Teklif adı, sıra sayısı ya da tarih" autocomplete="off"></div>
<p class="not" id="sayac" style="margin-top:8px" aria-live="polite"></p>
{ay_gruplari(sirali, lambda v: v["date"], oylama_satiri) or bos("Henüz açık oylama yok", "Bu yasama yılında açık oylama yapıldığında burada görünecek.")}
<p class="not" style="margin-top:30px">Yalnızca açık oylamalar listelenir. İşaretle (el kaldırarak) yapılan oylamalarda milletvekillerinin oyları kayda geçmez. <a href="yontem.html">Yöntem</a></p>
</div>"""
    return S.sayfa("Oylamalar · Meclis Tutanakları", govde, sekme="oylamalar", modul="liste.js")


# ---------- Oturum sayfası ----------

def neyle_ilgili(v: dict, kisa: bool = False) -> str:
    ss = v.get("ss")
    if not ss or ss.get("bulunamadi"):
        return ""
    no = ss["sira_sayisi"]
    pdf = A.guvenli_url(ss.get("pdf"))
    kaynak = (f'<a href="{escape(pdf)}" target="_blank" rel="noopener">S. Sayısı {escape(no)} komisyon raporu (PDF) ↗</a>'
              if pdf else f"S. Sayısı {escape(no)}")
    if "buyuk_pdf_mb" in ss:
        return "" if kisa else (f'<section class="bolum"><h2>Bu oylama neyle ilgili?</h2><p class="not">Komisyon raporu çok büyük '
                                f'({ss["buyuk_pdf_mb"]} MB; bütçe ya da kesin hesap) olduğu için gerekçesi otomatik çıkarılmadı. {kaynak}</p></section>')
    maddeler = ss.get("maddeler", [])
    asil = [m for m in maddeler if not m["rutin"]]
    rutin = [m for m in maddeler if m["rutin"]]
    ana = ss.get("esaslar") or ss.get("amac") or [m["ilk"] for m in asil]
    if not ana and not maddeler:
        return ""
    if kisa:
        return f'<ul style="margin:6px 0 0;padding-left:18px;font-size:15px;line-height:23px">{"".join(f"<li>{escape(x)}</li>" for x in ana[:3])}</ul>'
    etiketler = []
    if ss.get("kanun_no"):
        etiketler.append(f'<span class="etiket kesin">Kanun No {escape(ss["kanun_no"])}</span>')
    esas = re.search(r"\((\d/\d+)\)", ss.get("baslik", ""))
    if esas:
        etiketler.append(f'<span class="etiket cizgili">Esas No {escape(esas.group(1))}</span>')
    madde_html = ""
    if asil:
        items = "".join(f'<li style="margin-bottom:8px"><details><summary style="cursor:pointer"><b>Madde {escape(m["no"])}</b> {escape(m["ilk"])}</summary>'
                        f'<p class="not" style="margin:6px 0 4px 14px">{escape(m["metin"])}</p></details></li>' for m in asil)
        rutin_not = (f'<p class="not">Ayrıca {len(rutin)} rutin madde: '
                     + ", ".join(f"Madde {escape(m['no'])}" for m in rutin) + " (tanımlar, yürürlük, yürütme).</p>") if rutin else ""
        madde_html = (f'<details class="on-bilgi"><summary>Madde madde gerekçeler ({len(asil)} madde)</summary>'
                      f'<ol style="list-style:none;padding:0;margin:8px 0;font-size:15px;line-height:23px">{items}</ol>{rutin_not}</details>')
    genel = ss.get("genel_gerekce", "")
    genel_html = ""
    if genel:
        cumleler = [c.strip() for c in re.split(r"(?<=[a-zçğıöşüâîû\)’'\.]\.)\s+(?=[A-ZÇĞİÖŞÜ\"“(])", genel) if c.strip()]
        paras = [" ".join(cumleler[i:i + 3]) for i in range(0, len(cumleler), 3)]
        genel_html = ('<details class="on-bilgi"><summary>Genel gerekçenin tamamı</summary><div class="metin" style="font-size:16px">'
                      + "".join(f"<p>{escape(p)}</p>" for p in paras) + "</div></details>")
    return f"""<section class="bolum"><h2>Bu oylama neyle ilgili?</h2>
<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">{''.join(etiketler)}</div>
<ul class="metin" style="padding-left:20px;margin:0 0 10px;font-size:17px">{''.join(f'<li style="margin-bottom:8px">{escape(x)}</li>' for x in ana)}</ul>
{madde_html}{genel_html}
<p class="not" style="margin-top:10px">Kaynak: {kaynak}. Maddeler resmî gerekçeden değiştirilmeden alınmıştır; gerekçe teklifin ilk hâline aittir, komisyonda ya da Genel Kurul'da yapılan değişiklikler yansımamış olabilir.</p></section>"""


def tutanak_metni(s: dict, index: dict) -> str:
    doc, parcalar, cur = s["doc"], [], []

    def kapat():
        if cur:
            parcalar.append('<section class="parca">' + "".join(cur) + "</section>")
            cur.clear()

    for i, b in enumerate(doc["blocks"]):
        kind = b[0]
        if kind in ("oturum", "gundem"):
            kapat()
        if kind == "oturum":
            cur.append(f'<h2 class="oturum" id="b{i}">{escape(b[1])}</h2>')
        elif kind == "gundem":
            cur.append(f'<h3 class="gundem" id="b{i}">{escape(b[1])}</h3>')
        elif kind == "soz":
            _, name, place, devam, rest, sid, role = b
            if name == "BAŞKAN":
                ad = "Başkan"
            else:
                mi = akis.speaker_to_mp(name, place, index)
                gorunen = escape(A.tr_title(name))
                ad = f'<a href="mv-{akis_roster_id(mi)}.html">{gorunen}</a>' if mi is not None else gorunen
            ek = []
            if place:
                ek.append(escape(A.tr_title(place)) if place.isupper() else escape(place))
            if role:
                ek.append(escape(role))
            if devam:
                ek.append("devamla")
            yer = f' <span class="yer">· {" · ".join(ek)}</span>' if ek else ""
            cls = "soz baskan" if name == "BAŞKAN" else "soz"
            cur.append(f'<p class="{cls}" data-s="{sid}" id="b{i}"><span class="kim">{ad}{yer}</span>{A.inline(rest)}</p>')
        elif kind == "devam":
            cur.append(f'<p id="b{i}">{A.inline(b[1])}</p>')
        elif kind == "not":
            cur.append(f'<p class="ara-not" id="b{i}">{escape(b[1])}</p>')
        else:
            cur.append(f'<p id="b{i}">{A.inline(b[1])}</p>')
    kapat()
    on = ""
    if doc["front"]:
        on = ('<details class="on-bilgi"><summary>Kapak, içindekiler ve ön bilgiler</summary><div style="font-size:.85em;color:var(--murekkep-2)">'
              + "".join(f"<p>{escape(x)}</p>" for x in doc["front"]) + "</div></details>")
    return on + "".join(parcalar)


_ROSTER: list = []


def akis_roster_id(i: int) -> str:
    return _ROSTER[i][0]


def oturum_sayfasi(s: dict, ortak: dict) -> str:
    index = ortak["index"]
    ust = DONEM_YIL.format(donem=s["donem"], yil=s["yil"])
    ham = ""
    if A.durum_kodu(s["durum"]) == "ham":
        ham = ('<p class="not" style="margin-top:10px">TBMM bu metni “stenograflar tarafından deşifre edilmiş, uzman incelemesinden '
               'geçmemiş” ham tutanak olarak yayımlıyor. Kesin hâli yayımlandığında bu sayfa kendiliğinden güncellenir.</p>')
    # Özet sekmesi
    kararlar = ""
    if s["decisions"]:
        kararlar = ('<section class="bolum"><h2>Alınan kararlar</h2><ul class="liste">'
                    + "".join(f'<li class="satir" style="font:400 16.5px/25px var(--serif)">{escape(x)}</li>' for x in s["decisions"])
                    + '</ul><p class="not" style="margin-top:8px">TBMM tutanak özetinden, değiştirilmeden.</p></section>')
    oylamalar = ""
    if s["votes"]:
        oylamalar = ('<section class="bolum"><h2>Açık oylamalar</h2><ul class="liste">'
                     + "".join(oylama_satiri(v, oturum_goster=False, ek=neyle_ilgili(v, kisa=True)) for v in s["votes"]) + "</ul></section>")
    konusanlar = sorted(((sid, sp) for sid, sp in s["doc"]["speakers"].items() if sp["name"] != "BAŞKAN"),
                        key=lambda x: -x[1]["words"])
    konusan_html = ""
    if konusanlar:
        konusan_html = ('<section class="bolum"><h2>En çok konuşanlar</h2><ul class="liste">'
                        + "".join(f'<li class="satir" style="padding:10px 0"><a href="#konusmaci={sid}" style="display:flex;justify-content:space-between;gap:10px">'
                                  f'<span>{escape(A.tr_title(sp["name"]))} <small style="color:var(--murekkep-3)">{escape(A.tr_title(sp["place"]) if sp["place"].isupper() else sp["place"])}</small></span>'
                                  f'<span class="say" style="color:var(--murekkep-2)">{sp["count"]} söz</span></a></li>' for sid, sp in konusanlar[:8])
                        + f'</ul><p class="not" style="margin-top:8px">Toplam {len(konusanlar)} konuşmacı. Tümü için Tutanak sekmesindeki <b>Konuşmacılar</b>.</p></section>')
    ozet_metni = ""
    if s["ozet"]:
        ozet_metni = ('<details class="on-bilgi" style="margin-top:20px"><summary>TBMM tutanak özetinin tamamı</summary><div class="metin" style="font-size:16px">'
                      + "".join(f"<p>{escape(x)}</p>" for x in s["ozet"].split("\n") if x.strip()) + "</div></details>")
    if not (kararlar or oylamalar or konusan_html or ozet_metni):
        ozet_panel = bos("Bu birleşim için özet yok", "Tutanak sekmesinden metnin tamamını okuyabilirsiniz.")
    else:
        ozet_panel = kararlar + oylamalar + konusan_html + ozet_metni

    # Tutanak sekmesi
    if s["has_text"]:
        tutanak_panel = f'<div class="metin" id="metin">{tutanak_metni(s, index)}</div>'
    else:
        pdf = A.guvenli_url(s["src"].get("pdf"))
        tutanak_panel = bos("Metin yalnızca PDF olarak var",
                            "Bu dönemin tutanağı TBMM tarafından yalnızca PDF olarak yayımlanmış.",
                            f'<a class="dugme" href="{escape(pdf)}" target="_blank" rel="noopener">PDF\'i aç ↗</a>' if pdf else "")
    oy_panel = ('<ul class="liste">' + "".join(oylama_satiri(v, oturum_goster=False) for v in s["votes"]) + "</ul>") if s["votes"] \
        else bos("Bu birleşimde açık oylama yapılmadı", "Oylamalar işaretle (el kaldırarak) yapıldıysa milletvekillerinin oyları kayda geçmez.")

    toc = "".join(f'<li><a href="#b{i}" style="display:block;padding:8px 0;{"font-weight:600" if k == "oturum" else "padding-left:12px;color:var(--murekkep-2)"}">'
                  f'{escape(t if len(t) < 150 else t[:147] + "…")}</a></li>' for k, t, i in s["doc"]["toc"]) \
        or '<li class="not">Bu tutanakta başlık yok.</li>'
    kon = "".join(f'<li><button data-s="{sid}" style="display:flex;justify-content:space-between;width:100%;min-height:44px;border:0;border-bottom:1px solid var(--cizgi);background:none;text-align:left;font:400 15px/1.3 var(--sans);cursor:pointer">'
                  f'<span>{escape(A.tr_title(sp["name"]) if sp["name"] != "BAŞKAN" else "Başkan")} <small style="color:var(--murekkep-3)">{escape(A.tr_title(sp["place"]) if sp["place"].isupper() else sp["place"])}</small></span>'
                  f'<em style="font-style:normal;color:var(--murekkep-2)" class="say">{sp["count"]}</em></button></li>'
                  for sid, sp in sorted(s["doc"]["speakers"].items(), key=lambda x: -x[1]["words"]))
    boyutlar = "".join(f'<button data-boyut="{b}" aria-selected="false" aria-label="{b} piksel">{b}</button>' for b in (16, 18, 20, 22))
    atif = f"TBMM Genel Kurul Tutanağı, {ust}, {s['birlesim']}. Birleşim, {A.tarih_yazi(s['date'])}. {s['tbmm_url']}"
    indirildi = s.get("indirildi", "")[:16].replace("T", " ")

    govde = f"""<div data-okundu="{escape(s['read_id'])}" hidden></div>
<div class="kap"><div class="baslik"><p class="ust-etiket">{ust} · Genel Kurul</p><h1>{s['birlesim']}. Birleşim</h1>
<p class="alt">{escape(A.tarih_yazi(s['date']))} &nbsp;{durum_etiketi(s['durum'])}</p>{ham}</div>
<div class="sekmeler" role="tablist">
  <a href="#ozet" role="tab" data-sekme="ozet" aria-selected="true">Özet</a>
  <a href="#tutanak" role="tab" data-sekme="tutanak" aria-selected="false">Tutanak</a>
  <a href="#oylamalar" role="tab" data-sekme="oylamalar" aria-selected="false">Oylamalar{f' ({len(s["votes"])})' if s['votes'] else ''}</a></div></div>
{'<div class="arac" id="arac" hidden><div class="kap"><button id="ac-icindekiler">İçindekiler</button><button id="ac-konusmacilar">Konuşmacılar</button><button id="ac-ara">Ara</button><button id="ac-yazi" aria-label="Yazı boyutu">Aa</button>'
 '<div class="ara-kutu" id="ara-kutu" hidden><label class="gizli-metin" for="q">Metinde ara</label><input class="alan" id="q" type="search" placeholder="Metinde ara" autocomplete="off"><span id="sayac" aria-live="polite"></span>'
 '<button id="onceki" aria-label="Önceki sonuç">↑</button><button id="sonraki" aria-label="Sonraki sonuç">↓</button></div></div></div>' if s['has_text'] else ''}
<div class="kap">
<section class="panel" id="p-ozet" role="tabpanel">{ozet_panel}</section>
<section class="panel" id="p-tutanak" role="tabpanel" hidden>{tutanak_panel}</section>
<section class="panel" id="p-oylamalar" role="tabpanel" hidden>{oy_panel}</section>
{S.kaynak_bilgisi([f"Kaynak: TBMM Genel Kurul Tutanağı · {ust} · {s['birlesim']}. Birleşim · {escape(s['durum'])}",
                   f"Alındı: {escape(indirildi)} (Türkiye saati)" if indirildi else ""], s["tbmm_url"], atif)}
</div>
<dialog class="sayfa-alt" id="icindekiler" aria-labelledby="ic-b"><div class="bas"><h2 id="ic-b">Bu tutanakta</h2><button class="dugme yalin" data-kapat>Kapat</button></div><div class="ic"><ul style="list-style:none;margin:0;padding:0">{toc}</ul></div></dialog>
<dialog class="sayfa-alt" id="konusmacilar" aria-labelledby="ko-b"><div class="bas"><h2 id="ko-b">Konuşmacılar ({len(s['doc']['speakers'])})</h2><button class="dugme yalin" data-kapat>Kapat</button></div><div class="ic"><p class="not" style="margin-bottom:6px">Her dokunuşta kişinin bir sonraki konuşmasına gider.</p><ul style="list-style:none;margin:0;padding:0">{kon}</ul></div></dialog>
<dialog class="sayfa-alt" id="yazi" aria-labelledby="ya-b"><div class="bas"><h2 id="ya-b">Yazı boyutu</h2><button class="dugme yalin" data-kapat>Kapat</button></div><div class="ic"><div class="segment">{boyutlar}</div><p class="not" style="margin-top:10px">Tema ve diğer tercihler Takip sekmesinde.</p></div></dialog>
<button class="dugme basa-don" id="basa-don" hidden>↑ Başa dön</button>"""
    return S.sayfa(f"{s['birlesim']}. Birleşim · {A.tarih_yazi(s['date'])}", govde, sekme="oturumlar",
                   geri=("Oturumlar", "oturumlar.html"), modul="oturum.js")


# ---------- Oylama sayfası ----------

def oylama_sayfasi(v: dict, ortak: dict) -> str:
    s = v["oturum"]
    c = A.vote_counts(v)
    say = v.get("sayilar", {})
    resmi = [("Kabul", say.get("kabul")), ("Ret", say.get("ret")), ("Çekimser", say.get("cekimser")), ("Boş", say.get("bos")),
             ("Geçersiz", say.get("gecersiz")), ("Mükerrer", say.get("mukerrer")), ("Toplam", say.get("toplam"))]
    resmi_metin = " · ".join(f"{ad} {n}" for ad, n in resmi if n is not None)

    satirlar, isim_veri = [], []
    for parti, pc in A.party_table(v, ortak["sira"]):
        n = sum(pc.values())
        kimlik = "pi-" + S.parti_sinif(parti)
        ozet = " · ".join(f"{pc.get(k, 0)} {ad.lower()}" for k, ad, _, _ in S.OY_TURLERI if pc.get(k))
        satirlar.append(f'<button class="parti-satir" data-parti="{escape(parti)}" aria-expanded="false" aria-controls="{kimlik}">'
                        f'<span class="ad"><span>{S.parti_karesi(parti)}{escape(parti)} <small>{n}</small></span><small>{ozet}</small></span>'
                        f'{S.sayim(pc, etiket=False)}</button><div class="isimler" id="{kimlik}" hidden></div>')
    mv_satir = []
    partiler_bu = []
    for il, soyad, ad, parti, _s, pusula, sonuc, _t, saat_ in v["oylar"]:
        kod = A.oy_kodu(sonuc)
        p = A.PARTI_KISA.get(parti, parti)
        partiler_bu.append(p)
        tam = f"{A.tr_title(ad)} {A.tr_title(soyad)}"
        mid = akis.mp_id(tam, il)
        isim_veri.append([tam, A.tr_title(il), p, kod, mid])
        turu = next(((ad_, c_, i_) for k_, ad_, c_, i_ in S.OY_TURLERI if k_ == kod), ("Katılmadı", "x", "·"))
        mv_satir.append(f'<tr data-oy="{kod}" data-parti="{escape(p)}" data-mv="{mid}"><td><a href="mv-{mid}.html">{escape(tam)}</a></td>'
                        f'<td>{escape(A.tr_title(il))}</td><td>{escape(p)}</td>'
                        f'<td class="oy"><span class="isaret {turu[1]}" aria-hidden="true">{turu[2]}</span>{turu[0]}'
                        f'{" <small>(pusula)</small>" if pusula not in ("-", "") else ""}</td></tr>')
    secenekler = "".join(f'<option value="{escape(p)}">{escape(p)}</option>'
                         for p in sorted(set(partiler_bu), key=lambda x: (x == "Bağımsız", ortak["sira"].index(x) if x in ortak["sira"] else 99)))
    segment = '<button data-v="" aria-selected="true">Tümü</button>' + "".join(
        f'<button data-v="{k}" aria-selected="false">{ad} <span class="say">{c.get(k, 0)}</span></button>'
        for k, ad, _, _ in S.OY_TURLERI if c.get(k))
    ss_no = A.sira_no(v)
    baslik = A.temiz_baslik(v["baslik"])
    atif = f"TBMM Genel Kurulu açık oylama: {baslik}. {s['birlesim']}. Birleşim, {v['tarih_yazi']}. {v.get('kaynak', '')}"
    kaynak_url = A.guvenli_url(v.get("kaynak"))

    govde = f"""<div class="kap">
<div class="baslik"><p class="ust-etiket">Açık oylama · {escape(v['tarih_yazi'])}{' · ' + saat(v) if saat(v) else ''}</p>
<h1 style="font-size:25px;line-height:32px">{escape(baslik)}</h1>
<p class="alt">{f'Sıra sayısı {escape(ss_no)} · ' if ss_no else ''}{escape(v.get('bolum') or '')}</p></div>
<div style="padding:15px 0;border-top:1px solid var(--murekkep);border-bottom:1px solid var(--cizgi)">
  <p style="font:600 22px/28px var(--serif);margin-bottom:10px">{escape(v['sonuc'] or 'Sonuç belirtilmemiş')}</p>
  {S.sayim(c, sinif="kalin")}
  <p class="not" style="margin-top:10px">Resmî sonuç: {escape(resmi_metin)}. Katılmadı sayısı oy listesinden hesaplanmıştır.</p>
  <p class="not" style="margin-top:4px"><span class="etiket cizgili">Açık oylama</span> Her milletvekilinin oyu kayıtlıdır; partiler oylama tarihindeki üyeliğe göredir.</p>
</div>
{neyle_ilgili(v)}
<section class="bolum"><h2>Partilere göre</h2><p class="not" style="margin-bottom:6px">Sıralama: güncel sandalye sayısı. Bir partiye dokunun: o partiden kimin ne oy verdiği açılır.</p>
{''.join(satirlar)}</section>
<section class="bolum"><h2>Milletvekilleri ({len(v['oylar'])})</h2>
<div class="segment" id="oy-segment" role="tablist" aria-label="Oya göre süz">{segment}</div>
<div style="display:grid;grid-template-columns:1fr auto;gap:8px;margin:10px 0">
  <label class="gizli-metin" for="mv-ara">İsim ya da il ara</label><input class="alan" id="mv-ara" type="search" placeholder="İsim ya da il" autocomplete="off">
  <label class="gizli-metin" for="parti-sec">Parti</label><select class="alan" id="parti-sec" style="width:auto"><option value="">Tüm partiler</option>{secenekler}</select></div>
<p class="not" id="mv-sayac" aria-live="polite"></p>
<div style="overflow-x:auto"><table class="cetvel" id="mv-liste"><thead><tr><th scope="col">Milletvekili</th><th scope="col">İl</th><th scope="col">Parti</th><th scope="col">Oy</th></tr></thead>
<tbody>{''.join(mv_satir)}</tbody></table></div>
<p class="not" style="margin-top:8px">Takip ettiğiniz milletvekilleri listenin başında ● ile gösterilir.</p></section>
{S.kaynak_bilgisi([f"Kaynak: TBMM Açık Oylama Sonuçları · {DONEM_YIL.format(donem=v['donem'], yil=v['yil'])} · {v['birlesim']}. Birleşim"],
                   kaynak_url, atif, '<button class="dugme yalin" id="csv">CSV indir</button>')}
</div>
{S.veri_blogu("oylama-veri", {"id": v["read_id"], "oylar": isim_veri})}"""
    return S.sayfa(f"{baslik[:70]} · Açık oylama", govde, sekme="oylamalar",
                   geri=(f"{v['birlesim']}. Birleşim", s["page"] + "#oylamalar"), modul="oylama.js")


# ---------- Milletvekili, parti, il ----------

def mv_sayfasi(i: int, m: list, oylar: list, konusmalar: list) -> str:
    mid, ad, il, parti = m
    oy_html = "".join(
        f'<li class="satir"><a href="{v["page"]}"><div class="bilgi"><span>{kisa_tarih(v["date"])} · {v["birlesim"]}. Birleşim</span>'
        + (f'<span>Oylama tarihinde: {escape(p_o_an)}</span>' if p_o_an != parti else "")
        + f'</div><h3 style="font-size:17px;line-height:23px">{escape(A.temiz_baslik(v["baslik"]))}</h3>'
        f'<p style="margin-top:6px;font:600 15px/20px var(--sans)"><span class="isaret {kod_cls}" aria-hidden="true">{isaret}</span>{oy_adi}</p></a></li>'
        for v, oy_adi, kod_cls, isaret, p_o_an in oylar)
    kon_html = "".join(
        f'<li class="satir"><a href="{s["page"]}#konusmaci={sid}"><div class="bilgi"><span>{s["birlesim"]}. Birleşim</span></div>'
        f'<h3 style="font-size:17px;line-height:23px">{escape(A.tarih_yazi(s["date"]))}</h3><p class="govde">{n} söz</p></a></li>'
        for s, n, sid in konusmalar)
    govde = f"""<div class="kap">
<div class="baslik"><p class="ust-etiket">Milletvekili</p><h1>{escape(ad)}</h1>
<p class="alt"><a href="il-{A.slug(il)}.html">{escape(il)}</a> · {S.parti_karesi(parti)} <a href="parti-{A.slug(parti)}.html">{escape(parti)}</a></p>
<div style="margin-top:15px"><button class="dugme takip-dugme" data-tur="mv" data-id="{mid}">Takip et</button></div></div>
<p class="not">Bu dönemde {len(konusmalar)} oturumda konuştu · {len(oylar)} açık oylamada adı geçiyor.</p>
<section class="bolum"><h2>Açık oylamalardaki oyları ({len(oylar)})</h2>{f'<ul class="liste">{oy_html}</ul>' if oylar else '<p class="not">Kayıtlı açık oylama yok.</p>'}</section>
<section class="bolum"><h2>Genel Kurul konuşmaları ({len(konusmalar)} oturum)</h2>{f'<ul class="liste">{kon_html}</ul>' if konusmalar else '<p class="not">Kayıtlı konuşma yok.</p>'}</section>
<p class="not" style="margin-top:30px">Parti bilgisi en son açık oylamadaki üyeliğe göredir; her oylamada o tarihteki parti ayrıca gösterilir. <a href="yontem.html">Yöntem</a></p>
</div>"""
    return S.sayfa(f"{ad} · Meclis Tutanakları", govde, geri=("Ara", "ara.html"))


def grup_sayfasi(tur: str, ad: str, uyeler: list, votes: list, ortak: dict) -> str:
    """tur: 'parti' ya da 'il'. Üyeler [id, ad, il, parti]."""
    # Parti sayfasında milletvekilleri ile, il sayfasında partiye göre (sandalye sırasıyla) gruplanır
    gruplar = defaultdict(list)
    for m in uyeler:
        gruplar[m[2] if tur == "parti" else m[3]].append(m)
    if tur == "parti":
        sirali = sorted(gruplar.items(), key=lambda kv: akis.tr_anahtar(kv[0]))
        ust, alt = "Parti", f"{len(uyeler)} milletvekili · Sayılar en son açık oylamadaki üyeliğe göredir."
    else:
        sirali = sorted(gruplar.items(), key=lambda kv: (kv[0] == "Bağımsız", ortak["sira"].index(kv[0]) if kv[0] in ortak["sira"] else 99))
        ust, alt = "İl", f"{len(uyeler)} milletvekili"
    uye_html = "".join(
        f'<h3 class="ust-etiket" style="margin:15px 0 0">{S.parti_karesi(g) if tur == "il" else ""} {escape(g)} ({len(l)})</h3><ul class="liste">'
        + "".join(f'<li class="satir" style="padding:10px 0"><a href="mv-{m[0]}.html">{escape(m[1])}</a></li>'
                  for m in sorted(l, key=lambda m: akis.tr_anahtar(m[1])))
        + "</ul>" for g, l in sirali)
    oy_html = []
    for v in sorted(votes, key=lambda v: (v["date"], v["baslangic"] or ""), reverse=True):
        alt_say = [0, 0, 0, 0]
        for il, soyad, a_, parti, *_r in v["oylar"]:
            p = A.PARTI_KISA.get(parti, parti)
            if (tur == "parti" and p == ad) or (tur == "il" and A.tr_title(il) == ad):
                alt_say["KRCX".find(akis.OY_HARF.get(A.oy_kodu(_r[2]), "X"))] += 1
        if sum(alt_say):
            oy_html.append(oylama_satiri(v, sayim_veri=alt_say))
    kimlik = ad
    govde = f"""<div class="kap">
<div class="baslik"><p class="ust-etiket">{ust}</p><h1>{escape(ad)}</h1><p class="alt">{escape(alt)}</p>
<div style="margin-top:15px"><button class="dugme takip-dugme" data-tur="{tur}" data-id="{escape(kimlik)}">Takip et</button></div></div>
<section class="bolum"><h2>Açık oylamalarda {escape(ad)} {"grubu" if tur == "parti" else "milletvekilleri"}</h2>
<p class="not" style="margin-bottom:6px">Çubuk yalnızca bu {"partinin" if tur == "parti" else "ilin"} milletvekillerinin oylarını gösterir.</p>
{f'<ul class="liste">{"".join(oy_html)}</ul>' if oy_html else '<p class="not">Kayıtlı açık oylama yok.</p>'}</section>
<section class="bolum"><h2>Milletvekilleri</h2>{uye_html}</section>
</div>"""
    return S.sayfa(f"{ad} · Meclis Tutanakları", govde, geri=("Ara", "ara.html"))


# ---------- Ara, Takip, İlk açılış ----------

def ara_sayfasi() -> str:
    govde = """<div class="kap">
<div class="baslik"><h1>Ara</h1><p class="alt">Milletvekilleri, oylamalar ve tutanakların tam metni. Türkçe karakter gerekmez.</p></div>
<form id="ara-form" role="search"><label class="gizli-metin" for="q">Ara</label>
<input class="alan" id="q" type="search" placeholder="ör. asgari ücret, Özgür Özel, deprem" autocomplete="off" enterkeyhint="search"></form>
<div class="cipler" id="kapsam" role="group" aria-label="Arama kapsamı" hidden style="margin-top:12px">
  <button class="cip" data-v="" aria-pressed="true">Tümü <span class="say"></span></button>
  <button class="cip" data-v="mv" aria-pressed="false">Milletvekilleri <span class="say"></span></button>
  <button class="cip" data-v="O" aria-pressed="false">Oylamalar <span class="say"></span></button>
  <button class="cip" data-v="T" aria-pressed="false">Tutanaklar <span class="say"></span></button></div>
<div id="son" hidden><p class="ust-etiket" style="margin-top:25px">Son aramalarınız (bu cihazda)</p><ul class="liste" id="son-liste"></ul></div>
<div id="sonuc" aria-live="polite"></div>
</div>"""
    return S.sayfa("Ara · Meclis Tutanakları", govde, sekme="ara", modul="ara.js")


def takip_sayfasi(firebase_cfg: dict | None) -> str:
    saatler = [f"{h:02d}:00" for h in range(24)]
    sec = lambda i: f'<select class="alan" id="{i}" style="width:auto">' + "".join(f"<option>{s}</option>" for s in saatler) + "</select>"
    turler = [("oylama", "Oylamalar"), ("ozet", "Oturum özetleri ve kararlar"), ("konusma", "Konuşmalar"), ("teklif", "Kanun teklifleri ve gerekçeleri")]
    ritim = [("yakindan", "Yakından takip", "anlık, oturum başına en fazla 3"), ("gunluk", "Günlük özet", "önerilen"), ("haftalik", "Haftalık özet", "")]
    ayar = None
    if firebase_cfg:
        ayar = {"firebase": {k: firebase_cfg[k] for k in ("apiKey", "authDomain", "projectId", "appId") if k in firebase_cfg},
                "appcheck": firebase_cfg.get("appcheck_recaptcha_enterprise")}
    hesap = (f"""<section class="bolum" id="hesap"><h2>Hesap ve eşitleme</h2><div id="hesap-ic">
<p class="not">Takip listenizi başka cihazlarınızla eşitlemek için isteğe bağlı bir hesap açabilirsiniz. Uygulamayı kullanmak için gerekmez.</p>
<button class="dugme" id="hesap-ac" style="margin-top:12px">Hesap ile eşitle</button></div>{S.veri_blogu("firebase-ayar", ayar)}</section>"""
             if ayar else "")
    govde = f"""<div class="kap">
<div class="baslik"><h1>Takip</h1><p class="alt">Tercihleriniz bu cihazda saklanır.</p></div>
<section class="bolum"><h2>Takip ettikleriniz</h2><div id="takipler"><p class="not">Yükleniyor…</p></div>
<a class="dugme" href="hosgeldiniz.html?yeniden=1" style="margin-top:15px">Tercihlerimi yeniden ayarla</a></section>
<section class="bolum" id="plan"><h2>Bildirim planı</h2>
<p class="not" style="margin-bottom:6px">Bildirim gönderimi çok yakında açılacak; seçimleriniz şimdiden kaydedilir. Aynı seçimler akışınızı da belirler.</p>
<fieldset style="border:0;padding:0;margin:0"><legend class="gizli-metin">Bilgi türleri</legend>
{''.join(f'<div class="secenek"><label class="kutu"><input type="checkbox" data-tur="{k}"><span><b>{ad}</b></span></label></div>' for k, ad in turler)}</fieldset>
<fieldset style="border:0;padding:0;margin:15px 0 0"><legend class="ust-etiket">Ne sıklıkla</legend>
{''.join(f'<div class="secenek"><label class="kutu"><input type="radio" name="ritim" value="{k}"><span><b>{ad}</b>{f" <span>· {a}</span>" if a else ""}</span></label></div>' for k, ad, a in ritim)}</fieldset>
<div class="secenek" style="display:flex;flex-wrap:wrap;gap:10px;align-items:center"><b>Sessiz saatler</b>{sec("sessiz-bas")}<span aria-hidden="true">–</span>{sec("sessiz-bit")}</div></section>
<section class="bolum"><h2>Okuma</h2>
<p class="ust-etiket" style="margin:10px 0 6px">Tutanak yazı boyutu</p><div class="segment" id="boyut">{''.join(f'<button data-v="{b}" aria-selected="false">{b}</button>' for b in (16, 18, 20, 22))}</div>
<p class="ust-etiket" style="margin:15px 0 6px">Görünüm</p><div class="segment" id="tema"><button data-v="" aria-selected="true">Sistem</button><button data-v="acik" aria-selected="false">Açık</button><button data-v="koyu" aria-selected="false">Koyu</button></div></section>
<section class="bolum"><h2>Uygulama</h2><p class="not" id="uygulama-durum"></p><button class="dugme" id="yukle" hidden style="margin-top:10px">Uygulamayı yükle</button></section>
{hesap}
<section class="bolum"><h2>Verileriniz</h2>
<div style="display:flex;flex-wrap:wrap;gap:8px"><button class="dugme" id="indir">Verilerimi indir</button><button class="dugme tehlike" id="sil">Bu cihazdaki verileri sil</button></div></section>
<section class="bolum"><h2>Hakkında</h2><ul class="liste">
<li class="satir" style="padding:12px 0"><a href="yontem.html">Yöntem: veriler nereden geliyor, nasıl sıralanıyor</a></li>
<li class="satir" style="padding:12px 0"><a href="gizlilik.html">Gizlilik ve kişisel verilerin korunması</a></li>
<li class="satir" style="padding:12px 0"><a href="{S.REPO}/issues/new" target="_blank" rel="noopener">Hata bildir ↗</a></li>
<li class="satir" style="padding:12px 0"><a href="{S.REPO}" target="_blank" rel="noopener">Açık kaynak kodu ↗</a></li></ul></section>
</div>"""
    return S.sayfa("Takip · Meclis Tutanakları", govde, sekme="takip", modul="takip.js", firebase=bool(ayar))


def hosgeldiniz_sayfasi() -> str:
    govde = """<div class="kap">
<div class="adim-ust"><div class="ilerleme" id="ilerleme" role="img"></div><button class="dugme yalin" id="atla-hepsi">Şimdilik atla</button></div>
<section class="adim" id="adim" aria-live="polite"><p class="not" style="padding:30px 0">Yükleniyor…</p></section></div>
<div class="adim-alt"><div class="kap"><button class="dugme" id="geri" hidden>Geri</button><button class="dugme ana" id="ileri">Devam</button></div></div>"""
    return S.sayfa("Hoş geldiniz · Meclis Tutanakları", govde, modul="hosgeldiniz.js", nav=False)


# ---------- Yöntem, gizlilik, yönlendirme ----------

def yontem_sayfasi(ortak: dict) -> str:
    sira = ", ".join(f"{escape(p)} ({ortak['koltuk'][p]})" for p in ortak["sira"])
    konular = "".join(f"<li><b>{escape(ad)}</b>: {escape(', '.join(k))}</li>" for _, ad, k in akis.KONULAR)
    govde = f"""<div class="kap metin" style="font-size:17px">
<div class="baslik"><h1>Yöntem</h1><p class="alt" style="font-family:var(--sans)">Veriler nereden geliyor, nasıl işleniyor ve nasıl sıralanıyor.</p></div>
<h3 class="gundem">Kaynak</h3>
<p>Tüm içerik TBMM'nin kamuya açık yayınlarından otomatik olarak, günde iki kez alınır: Genel Kurul tutanakları ve özetleri, açık oylama sonuçları ve oylanan tekliflerin komisyon raporları (sıra sayıları). Her sayfanın altında TBMM'deki kaynağa bağlantı ve alınma zamanı bulunur.</p>
<h3 class="gundem">Tutanak aşamaları</h3>
<p><b>Ham tutanak</b>: TBMM'nin ifadesiyle “stenograflar tarafından deşifre edilmiş, uzman incelemesinden geçmemiş” metin. <b>Tam tutanak</b> ve <b>Basılmış</b> tutanak kesinleşmiş metinlerdir. Kesin metin yayımlandığında sayfa kendiliğinden güncellenir.</p>
<h3 class="gundem">Oylamalar</h3>
<p>Yalnızca <b>açık oylamalar</b> gösterilir; bunlarda her milletvekilinin oyu kayıtlıdır. İşaretle (el kaldırarak) yapılan oylamalarda kişi bazında oy kaydı yoktur. Her oylamada milletvekilinin partisi, oylama tarihindeki üyeliğine göre gösterilir. “Çekimser” ile “Katılmadı” ayrı tutulur.</p>
<p>Oylar renk yanında işaretle de gösterilir: ✓ Kabul (mavi), ✕ Ret (kızıl), – Çekimser, · Katılmadı. Bu renkler hiçbir partiyi temsil etmez ve renk körlüğüne uygun olarak seçilmiştir.</p>
<h3 class="gundem">Partilerin sıralaması ve renkleri</h3>
<p>Partiler her yerde aynı kurala göre sıralanır: en son açık oylamadaki üyeliğe göre <b>sandalye sayısı</b> (çoktan aza), eşitlikte alfabetik; bağımsızlar en sonda. Şu anki sıra: {sira}.</p>
<p>Parti renkleri yaklaşıktır ve yalnızca ayırt etmeye yardım eder; her zaman parti adıyla birlikte, küçük bir kare olarak gösterilir. Aynı renk ailesindeki partiler (ör. CHP ve Yeni Parti) desenle ayrılır. Uygulamanın kendi renkleri hiçbir partiyle ilişkili değildir.</p>
<h3 class="gundem">“Bu oylama neyle ilgili?”</h3>
<p>Oylanan teklifin komisyon raporundaki <b>resmî gerekçeden</b> cümleler değiştirilmeden alınır: genel gerekçedeki madde listesi varsa o, yoksa amacı bildiren cümleler; ayrıca madde madde gerekçeler. Yapay zekâ ile özet üretilmez. Gerekçe teklifin ilk hâline aittir; komisyonda ya da Genel Kurul'da yapılan değişiklikler yansımamış olabilir.</p>
<h3 class="gundem">Akış ve konular</h3>
<p>Akış, takip ettiğiniz il, milletvekili, parti, konu ve kelimelere göre <b>cihazınızda</b> hesaplanır; her kaydın altında neden gösterildiği yazar. Kelimeler tutanak metinlerinin tamamında, özetlerde ve gerekçelerde kelime başından eşleşir (“emekli” yazınca “emekliler” de bulunur). Konular şu kelimeleri arar:</p>
<ul>{konular}</ul>
<h3 class="gundem">Hatalar ve düzeltmeler</h3>
<p>Bir hata görürseniz her sayfanın altındaki <b>Hata bildir</b> bağlantısını kullanın. Kaynak kodu ve tüm değişikliklerin geçmişi <a href="{S.REPO}">açık</a>tır.</p>
</div>"""
    return S.sayfa("Yöntem · Meclis Tutanakları", govde, geri=("Takip", "takip.html"))


def gizlilik_sayfasi() -> str:
    govde = """<div class="kap metin" style="font-size:17px">
<div class="baslik"><h1>Gizlilik ve kişisel verilerin korunması</h1></div>
<p class="not" style="font-family:var(--sans)"><span class="etiket ham">Taslak</span> Bu metin uygulamanın teknik olarak hangi verileri işlediğini açıklar; yayın öncesinde hukuki incelemeden geçmiş aydınlatma metniyle değiştirilecektir.</p>
<h3 class="gundem">Hesapsız kullanım</h3>
<p>Uygulamayı kullanmak için hesap gerekmez. Takip listeniz, bildirim planınız, okuma tercihleriniz ve okundu işaretleriniz <b>yalnızca bu cihazda</b> (tarayıcı deposunda) saklanır ve hiçbir sunucuya gönderilmez. Takip sekmesinden indirebilir ya da silebilirsiniz.</p>
<h3 class="gundem">İsteğe bağlı hesap</h3>
<p>Yalnızca cihazlar arası eşitleme için hesap açabilirsiniz. Bu durumda e-posta adresiniz (giriş için), takip listeniz, bildirim planınız ve okundu işaretleriniz Google Firebase'de (Authentication ve Cloud Firestore; veritabanı Avrupa Birliği'nde, eur3 bölgesinde) saklanır. Bu, verilerin yurt dışına aktarılması anlamına gelir. Verilerinize yalnızca siz erişebilirsiniz.</p>
<h3 class="gundem" id="riza">Açık rıza</h3>
<p>Takip ettiğiniz milletvekilleri ve partiler siyasi görüşünüzü dolaylı olarak gösterebileceğinden, bu bilgiler sunucuya ancak hesap açarken ayrıca işaretlediğiniz açık rıza ile gönderilir. Rıza vermeseniz de uygulamanın tamamını hesapsız kullanabilirsiniz. Rızanızı istediğiniz zaman <b>Takip → Hesap → Hesabımı ve sunucudaki verilerimi sil</b> ile geri alabilirsiniz.</p>
<h3 class="gundem">Çerezler ve izleme</h3>
<p>Uygulama reklam, analiz ya da izleme çerezi kullanmaz. Hesap bölümü açıldığında Google'ın güvenlik doğrulaması (reCAPTCHA Enterprise, Firebase App Check) yalnızca kötüye kullanımı önlemek için çalışır.</p>
<h3 class="gundem">Kaynak</h3>
<p>Tutanak ve oylama içerikleri TBMM'nin kamuya açık yayınlarından alınır.</p>
</div>"""
    return S.sayfa("Gizlilik · Meclis Tutanakları", govde, geri=("Takip", "takip.html"))


def yonlendirme_sayfasi() -> str:
    """Eski akis.html (önceki giriş bağlantıları ve yer imleri) yeni Takip sayfasına yönlenir."""
    govde = ('<div class="kap"><p class="bos">Bu sayfa taşındı. <a href="takip.html">Takip sekmesine gidin</a>.</p></div>'
             "<script>location.replace('takip.html'+location.search+location.hash)</script>")
    return S.sayfa("Takip · Meclis Tutanakları", govde, nav=False)


# ---------- Hepsi ----------

def hepsini_yaz(sessions: list[dict], votes: list[dict], ortak: dict, out: Path) -> set[str]:
    global _ROSTER
    _ROSTER = ortak["roster"]
    yaz = lambda ad, html: (out / ad).write_text(html, encoding="utf-8")
    yazilan = set()

    def kaydet(ad, html):
        yaz(ad, html); yazilan.add(ad)

    import json as _json
    cfg_yol = A.ROOT / "firebase-web.json"
    cfg = _json.loads(cfg_yol.read_text(encoding="utf-8")) if cfg_yol.exists() else None

    kaydet("index.html", akis_sayfasi())
    kaydet("oturumlar.html", oturumlar_sayfasi(sessions))
    kaydet("oylamalar.html", oylamalar_sayfasi(votes))
    kaydet("ara.html", ara_sayfasi())
    kaydet("takip.html", takip_sayfasi(cfg))
    kaydet("hosgeldiniz.html", hosgeldiniz_sayfasi())
    kaydet("yontem.html", yontem_sayfasi(ortak))
    kaydet("gizlilik.html", gizlilik_sayfasi())
    kaydet("akis.html", yonlendirme_sayfasi())
    for s in sessions:
        kaydet(s["page"], oturum_sayfasi(s, ortak))
    for v in votes:
        kaydet(v["page"], oylama_sayfasi(v, ortak))

    # Milletvekili sayfaları: her oylamadaki oyu ve konuştuğu oturumlar
    roster, index = ortak["roster"], ortak["index"]
    mv_oylar: dict[int, list] = defaultdict(list)
    for v in sorted(votes, key=lambda v: (v["date"], v["baslangic"] or ""), reverse=True):
        for il, soyad, ad, parti, _s, _p, sonuc, _t, _h in v["oylar"]:
            i = index.get(akis.mp_id(f"{ad} {soyad}", il))
            if i is None:
                continue
            kod = A.oy_kodu(sonuc)
            ad_, cls, isaret = next(((a, c, i_) for k, a, c, i_ in S.OY_TURLERI if k == kod), ("Katılmadı", "x", "·"))
            mv_oylar[i].append((v, ad_, cls, isaret, A.PARTI_KISA.get(parti, parti)))
    for i, m in enumerate(roster):
        kon = sorted(ortak["konusmalar"].get(i, []), key=lambda x: x[0]["date"], reverse=True)
        kaydet(f"mv-{m[0]}.html", mv_sayfasi(i, m, mv_oylar.get(i, []), kon))
    for p in ortak["sira"]:
        kaydet(f"parti-{A.slug(p)}.html", grup_sayfasi("parti", p, [m for m in roster if m[3] == p], votes, ortak))
    for il in sorted({m[2] for m in roster}, key=akis.tr_anahtar):
        kaydet(f"il-{A.slug(il)}.html", grup_sayfasi("il", il, [m for m in roster if m[2] == il], votes, ortak))
    return yazilan
