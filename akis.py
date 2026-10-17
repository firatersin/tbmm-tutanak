#!/usr/bin/env python3
"""Uygulamanın tarayıcıda kullandığı veri dosyaları (site/veri/).

  site/veri/akis.json         milletvekili listesi, parti sandalye sayıları, konu listesi ve her tutanak/oylama için
                              kim konuştu, kim ne oy verdi, partilere/illere göre dağılım
  site/veri/kelime/<xx>.json  tam metin kelime dizini; ilk iki harfe göre bölünmüş (uygulama yalnızca
                              aranan/takip edilen kelimelerin parçasını indirir)

Akış, arama ve ilk açılıştaki önizleme bu dosyalardan tarayıcıda hesaplanır; kişisel tercihler cihazdan çıkmaz.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import arayuz as A
import sablon as S

TR_ASCII = str.maketrans("çğıöşü", "cgiosu")
OY_HARF = {"KABUL": "K", "RET": "R", "ÇEKİMSER": "C", "KATILMADI": "X"}

# İlk açılışta seçilebilen konular ve aradıkları kelimeler (kelime başı eşleşir). Yöntem sayfasında yayımlanır.
KONULAR = [
    ("ekonomi", "Ekonomi ve bütçe", ["enflasyon", "vergi", "bütçe", "faiz", "ekonomi"]),
    ("calisma", "Çalışma hayatı ve emeklilik", ["asgari ücret", "emekli", "işçi", "sendika", "istihdam"]),
    ("egitim", "Eğitim", ["eğitim", "okul", "öğretmen", "üniversite", "öğrenci"]),
    ("saglik", "Sağlık", ["sağlık", "hastane", "doktor", "ilaç"]),
    ("adalet", "Adalet ve hukuk", ["yargı", "mahkeme", "infaz", "anayasa"]),
    ("dis", "Dış ilişkiler", ["dışişleri", "uluslararası", "büyükelçi"]),
    ("cevre", "Çevre ve enerji", ["çevre", "iklim", "enerji", "maden", "orman"]),
    ("tarim", "Tarım ve gıda", ["tarım", "çiftçi", "hayvancılık", "gıda"]),
    ("yerel", "Yerel yönetimler ve imar", ["belediye", "yerel yönetim", "imar"]),
    ("afet", "Afet ve deprem", ["deprem", "afet"]),
    ("ulastirma", "Ulaştırma", ["ulaştırma", "karayolu", "demiryolu", "havalimanı"]),
    ("sosyal", "Aile ve sosyal politika", ["aile", "kadın", "çocuk", "engelli", "sosyal yardım"]),
]


# ---------- Kelime dizini (Python ve JS aynı normalleştirmeyi kullanmalı) ----------

def norm(s: str) -> str:
    s = s.replace("I", "ı").replace("İ", "i").lower()
    return s.replace("â", "a").replace("î", "i").replace("û", "u")


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zçğıöşü0-9]+", norm(text)) if 3 <= len(t) <= 30}


def shard_key(token: str) -> str:
    return token[:2].translate(TR_ASCII)


# ---------- Milletvekilleri ----------

def mp_id(name: str, il: str) -> str:
    return f"{A.slug(name)}--{A.slug(il)}"


def build_roster(votes: list[dict]) -> tuple[list[list[str]], dict[str, int]]:
    """En yeni oylamadan geriye: her milletvekilinin kimliği, adı, ili ve en güncel partisi."""
    roster, index = [], {}
    for v in sorted(votes, key=lambda x: (x["date"], x["baslangic"]), reverse=True):
        for il, soyad, ad, parti, *_ in v["oylar"]:
            key = mp_id(f"{ad} {soyad}", il)
            if key not in index:
                index[key] = len(roster)
                roster.append([key, f"{A.tr_title(ad)} {A.tr_title(soyad)}", A.tr_title(il), A.PARTI_KISA.get(parti, parti)])
    return roster, index


def speaker_to_mp(name: str, place: str, index: dict[str, int]) -> int | None:
    """Tutanaktaki konuşmacıyı listeye bağlar.

    'ADALET BAKANI YILMAZ TUNÇ' gibi unvanlı adlarda sondaki kelimeleri dener. Oylama listesinde çift soyadıyla
    ('Perihan KOCA DOĞAN') geçip tutanakta kısaltılanlar ('PERİHAN KOCA') için aynı ilde soyadı ve adın başıyla
    eşleştirir; yalnızca tek aday varsa kabul eder.
    """
    if not place:
        return None
    words = name.split()
    for n in range(len(words), 1, -1):
        i = index.get(mp_id(" ".join(words[-n:]), place))
        if i is not None:
            return i
    if len(words) < 2:
        return None
    il, soyad, ad = A.slug(place), A.slug(words[-1]), A.slug(words[0])[:3]
    adaylar = {i for key, i in index.items()
               if key.endswith("--" + il) and soyad in key.split("--")[0].split("-")[1:]
               and key.startswith(ad)}
    return adaylar.pop() if len(adaylar) == 1 else None


TR_SIRA = str.maketrans("ÇĞİÖŞÜçğıöşü", "CGIOSUcgiosu")


def tr_anahtar(s: str) -> str:
    """Türkçe alfabetik sıralama için yaklaşık anahtar (Ç, C'den hemen sonra gelir)."""
    harfler = "aâbcçdefgğhıiîjklmnoöprsştuüûvyz"
    return "".join(chr(0x100 + harfler.index(c)) if c in harfler else c for c in norm(s))


def parti_sirasi(koltuk: Counter) -> list[str]:
    """Yayımlanan kural: güncel sandalye sayısı (çoktan aza), eşitlikte alfabetik; bağımsızlar en sonda."""
    return sorted(koltuk, key=lambda p: (p == "Bağımsız", -koltuk[p], tr_anahtar(p)))


def mp_konusmalari(sessions: list[dict], index: dict[str, int]) -> dict[int, list]:
    """Her milletvekilinin konuştuğu oturumlar: [(oturum, konuşma sayısı, konuşmacı kimliği)]."""
    out: dict[int, list] = defaultdict(list)
    for s in sessions:
        for sid, sp in s["doc"]["speakers"].items():
            i = speaker_to_mp(sp["name"], sp["place"], index)
            if i is not None:
                out[i].append((s, sp["count"], sid))
    return out


# ---------- Veri dosyaları ----------

def build_data(sessions: list[dict], votes: list[dict], out: Path) -> dict:
    roster, index = build_roster(votes)
    koltuk = Counter(r[3] for r in roster)
    sira = parti_sirasi(koltuk)
    surum = datetime.now(A.TR_TZ).strftime("%Y%m%d%H%M%S")

    items, texts = [], []
    for s in sorted(sessions, key=lambda x: (x["date"], x["donem"], x["yil"], x["birlesim"])):
        konusan, parti_k, il_k = {}, Counter(), Counter()
        for sid, sp in s["doc"]["speakers"].items():
            i = speaker_to_mp(sp["name"], sp["place"], index)
            if i is None:
                continue
            konusan[str(i)] = [sp["count"], sid]
            parti_k[roster[i][3]] += 1
            il_k[roster[i][2]] += 1
        items.append({
            "t": "T", "id": s["read_id"], "p": s["page"], "d": s["date"].strftime("%Y-%m-%d"), "s": "",
            "bn": s["birlesim"], "b": f"{s['birlesim']}. Birleşim", "l": s["lead"], "du": s["durum"],
            "ko": len(s["doc"]["speakers"]), "n": len(s["votes"]),
            "k": konusan, "pk": dict(parti_k), "ik": dict(il_k),
        })
        texts.append(s["ozet"] + "\n" + (s["txt"].read_text(encoding="utf-8") if s["has_text"] else ""))

        for v in sorted(s["votes"], key=lambda x: (x["baslangic"], x["no"])):
            oy = ["-"] * len(roster)
            pv, iv = defaultdict(lambda: [0, 0, 0, 0]), defaultdict(lambda: [0, 0, 0, 0])
            toplam = [0, 0, 0, 0]
            for il, soyad, ad, parti, _s, _p, sonuc, _t, _h in v["oylar"]:
                code = A.oy_kodu(sonuc)
                col = "KRCX".find(OY_HARF.get(code, "X"))
                toplam[col] += 1
                pv[A.PARTI_KISA.get(parti, parti)][col] += 1
                iv[A.tr_title(il)][col] += 1
                i = index.get(mp_id(f"{ad} {soyad}", il))
                if i is not None:
                    oy[i] = OY_HARF.get(code, "X")
            ss = v.get("ss") or {}
            ana = ss.get("esaslar") or ss.get("amac") or []
            items.append({
                "t": "O", "id": v["read_id"], "p": v["page"], "d": v["date"].strftime("%Y-%m-%d"),
                "s": v["baslangic"][11:16] if v["baslangic"] else "", "bn": v["birlesim"],
                "b": A.temiz_baslik(v["baslik"]), "l": ana[0] if ana else "", "so": v["sonuc"], "to": toplam,
                "v": "".join(oy), "pv": dict(pv), "iv": dict(iv),
            })
            texts.append(" ".join([v["baslik"], ss.get("genel_gerekce", ""), " ".join(ana)]
                                  + [m["metin"] for m in ss.get("maddeler", [])]))

    shards: dict[str, dict[str, list[int]]] = defaultdict(dict)
    for i, text in enumerate(texts):
        for tok in tokens(text):
            shards[shard_key(tok)].setdefault(tok, []).append(i)

    veri = out / "veri"
    kel = veri / "kelime"
    kel.mkdir(parents=True, exist_ok=True)
    for old in kel.glob("*.json"):
        if old.stem not in shards:
            old.unlink()
    for key, posting in shards.items():
        (kel / f"{key}.json").write_text(json.dumps(posting, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    data = {
        "surum": surum,
        "mv": roster,
        "partiler": sira,
        "koltuk": dict(koltuk),
        "ps": {p: S.parti_sinif(p) for p in koltuk},
        "iller": sorted({r[2] for r in roster}, key=tr_anahtar),
        "konular": [[k, ad, kelimeler] for k, ad, kelimeler in KONULAR],
        "ogeler": items,
    }
    (veri / "akis.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"roster": roster, "index": index, "koltuk": koltuk, "sira": sira, "surum": surum}
