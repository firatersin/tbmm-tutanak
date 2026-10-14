#!/usr/bin/env python3
"""Kişisel akış: veri dosyaları (site/veri/), Akışım sayfası ve gizlilik sayfası.

arayuz.build() tarafından çağrılır. Herkese açık içerik statik kalır; kullanıcıya özel veriler
(takip edilenler, okundu işaretleri) Firebase'de tutulur ve akış tarayıcıda hesaplanır.

  site/veri/akis.json         milletvekili listesi + her tutanak/oylama için kim konuştu, kim ne oy verdi
  site/veri/kelime/<xx>.json  tam metin kelime dizini; ilk iki harfe göre bölünmüş (uygulama sadece
                              takip edilen kelimelerin parçasını indirir)
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
from pathlib import Path

import arayuz as A

ROOT = Path(__file__).resolve().parent
FIREBASE_CONFIG = ROOT / "firebase-web.json"
FIREBASE_SDK = "12.4.0"  # https://www.gstatic.com/firebasejs/<sürüm>/...

TR_ASCII = str.maketrans("çğıöşü", "cgiosu")
OY_HARF = {"KABUL": "K", "RET": "R", "ÇEKİMSER": "C", "KATILMADI": "X"}


# ---------- Kelime dizini (Python ve JS aynı normalleştirmeyi kullanmalı) ----------

def norm(s: str) -> str:
    s = s.replace("I", "ı").replace("İ", "i").lower()
    return s.replace("â", "a").replace("î", "i").replace("û", "u")


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zçğıöşü0-9]+", norm(text)) if 3 <= len(t) <= 30}


def shard_key(token: str) -> str:
    return token[:2].translate(TR_ASCII)


# ---------- Milletvekili kimlikleri ----------

def mp_id(name: str, il: str) -> str:
    return f"{A.slug(name)}--{A.slug(il)}"


def build_roster(votes: list[dict]) -> tuple[list[list[str]], dict[str, int]]:
    """En yeni oylamadan geriye: her milletvekilinin adı, ili ve (en güncel) partisi."""
    roster, index = [], {}
    for v in sorted(votes, key=lambda x: (x["date"], x["baslangic"]), reverse=True):
        for il, soyad, ad, parti, *_ in v["oylar"]:
            key = mp_id(f"{ad} {soyad}", il)
            if key not in index:
                index[key] = len(roster)
                roster.append([key, f"{A.tr_title(ad)} {soyad}", A.tr_title(il), A.PARTI_KISA.get(parti, parti)])
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


# ---------- Veri dosyaları ----------

def build_data(sessions: list[dict], votes: list[dict], out: Path) -> str:
    roster, index = build_roster(votes)
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
            "b": f"{s['birlesim']}. Birleşim tutanağı", "l": s["lead"], "du": s["durum"],
            "k": konusan, "pk": dict(parti_k), "ik": dict(il_k),
        })
        texts.append(s["ozet"] + "\n" + (s["txt"].read_text(encoding="utf-8") if s["has_text"] else ""))

        for v in sorted(s["votes"], key=lambda x: (x["baslangic"], x["no"])):
            oy = ["-"] * len(roster)
            pv, iv = defaultdict(lambda: [0, 0, 0, 0]), defaultdict(lambda: [0, 0, 0, 0])
            for il, soyad, ad, parti, _s, _p, sonuc, _t, _h in v["oylar"]:
                code = A.oy_kodu(sonuc)
                col = "KRCX".find(OY_HARF.get(code, "X"))
                pv[A.PARTI_KISA.get(parti, parti)][col] += 1
                iv[A.tr_title(il)][col] += 1
                i = index.get(mp_id(f"{ad} {soyad}", il))
                if i is not None:
                    oy[i] = OY_HARF.get(code, "X")
            ss = v.get("ss") or {}
            ana = ss.get("esaslar") or ss.get("amac") or []
            items.append({
                "t": "O", "id": v["read_id"], "p": v["page"], "d": v["date"].strftime("%Y-%m-%d"),
                "s": v["baslangic"][11:16] if v["baslangic"] else "",
                "b": v["baslik"], "l": ana[0] if ana else "", "so": v["sonuc"],
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
        "partiler": sorted({r[3] for r in roster}, key=lambda p: -sum(1 for r in roster if r[3] == p)),
        "iller": sorted({r[2] for r in roster}, key=lambda s: s.translate(str.maketrans("ÇĞİÖŞÜçğıöşü", "CGIOSUcgiosu"))),
        "ogeler": items,
    }
    (veri / "akis.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return surum


# ---------- Sayfalar ----------

def firebase_config() -> dict | None:
    if not FIREBASE_CONFIG.exists():
        return None
    return json.loads(FIREBASE_CONFIG.read_text(encoding="utf-8"))


AKIS_CSS = """
main.wrap{max-width:860px;margin:0 auto;padding:24px 16px 80px}
.ttl{font-weight:600}.bar-in #kim{margin-left:auto;font-size:13px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
h1{font-family:var(--serif);font-weight:normal;font-size:30px;margin:0 0 8px}
.kutu{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0}
.kutu h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 10px;font-weight:600}
form.satir,.satir{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.satir input,.satir select{flex:1;min-width:200px;font:inherit;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink)}
button.ana{background:var(--accent);color:#fff;border-color:var(--accent)}
.durum{font-size:14px;margin:10px 0 0}.durum.hata{color:var(--r)}.durum.ok{color:var(--bas)}
.muted{color:var(--muted)}.kucuk{font-size:13px}
.sekmeler{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:4px 0 14px}
.sekmeler button{border:0;border-bottom:2px solid transparent;border-radius:0;background:none;padding:8px 14px;color:var(--muted)}
.sekmeler button.on{border-bottom-color:var(--accent);color:var(--ink);font-weight:600}
.etiketler{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
.etiket{display:inline-flex;align-items:center;gap:6px;background:var(--bg);border:1px solid var(--line);border-radius:99px;padding:3px 6px 3px 12px;font-size:13px}
.etiket button{border:0;background:none;padding:0 6px;color:var(--muted);font-size:15px;line-height:1}
.secim{display:flex;flex-wrap:wrap;gap:6px}.secim button{border-radius:99px;padding:4px 12px;font-size:13px}
.secim button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.oneri{border:1px solid var(--line);border-radius:8px;background:var(--panel);max-height:240px;overflow:auto;margin-top:4px}
.oneri button{display:block;width:100%;text-align:left;border:0;border-radius:0;padding:7px 12px;font-size:14px}
.oneri button:hover{background:var(--accent-soft)}.oneri small{color:var(--muted)}
h3.gun{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:26px 0 10px;font-weight:600}
.kart{display:block;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin-bottom:10px;text-decoration:none}
.kart:hover{border-color:var(--accent)}.kart.unread{border-left:4px solid var(--accent)}
.kart .r1{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.kart .b{font-weight:600}
.kart .l{font-size:14px;margin:4px 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.neden{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.neden span{font-size:12.5px;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:2px 8px}
.neden a{color:var(--accent)}
.bos{color:var(--muted);text-align:center;padding:30px 10px}
.tehlike{border-color:var(--r);color:var(--r)}
#ios-panel{border-color:var(--accent)}
"""


def build_akis_page(cfg: dict | None, surum: str) -> str:
    body = """<div class="top"><div class="bar-in"><a class="home" href="index.html">← <b>Tüm kayıtlar</b></a>
<span class="ttl">Akışım</span><span id="kim"></span></div></div>
<main class="wrap">
<p id="yukleniyor" class="muted">Yükleniyor…</p>

<section id="kapali" hidden><h1>Akışım</h1>
<p class="muted">Hesaplar henüz yapılandırılmadı.</p></section>

<section id="ios-panel" class="kutu" hidden>
<h2>Uygulamada giriş yapın</h2>
<p>Bu giriş bağlantısı ana ekrandaki uygulamadan istendi. iPhone'da uygulama ve Safari ayrı oturum tutar.</p>
<ol><li>Aşağıdan bağlantıyı kopyalayın.</li><li>Ana ekrandaki <b>Meclis</b> uygulamasını açın.</li>
<li><b>Akışım → Bağlantıyı yapıştır</b> alanına yapıştırın.</li></ol>
<div class="satir"><button class="ana" id="ios-kopyala">Bağlantıyı kopyala</button>
<button id="ios-burada">Bunun yerine Safari'de giriş yap</button></div>
<p class="durum" id="ios-durum"></p></section>

<section id="giris" hidden>
<h1>Akışım</h1>
<p>Takip ettiğiniz milletvekili, parti, il ve konulara göre kişisel akışınızı görmek için giriş yapın.
Okumak için giriş gerekmez.</p>
<div class="kutu"><h2>E-posta ile giriş</h2>
<p class="kucuk muted">E-postanıza tek dokunuşla giriş bağlantısı gönderilir; şifre gerekmez.</p>
<form id="f-eposta" class="satir"><input type="email" id="eposta" required autocomplete="email" placeholder="ornek@eposta.com">
<button class="ana" type="submit">Giriş bağlantısı gönder</button></form>
<p class="durum" id="eposta-durum"></p>
<details id="yapistir"><summary class="kucuk">Bağlantıyı yapıştır (iPhone uygulaması)</summary>
<p class="kucuk muted">E-postadaki bağlantı Safari'de açıldıysa, bağlantıyı kopyalayıp buraya yapıştırın.</p>
<form id="f-yapistir" class="satir"><input id="link" placeholder="https://…" autocomplete="off">
<button type="submit">Giriş yap</button></form></details></div>
<div class="kutu" id="telefon" hidden><h2>Telefon ile giriş</h2>
<form id="f-tel" class="satir"><input type="tel" id="tel" placeholder="5xx xxx xx xx" inputmode="tel" autocomplete="tel-national">
<button class="ana" type="submit" id="tel-gonder">Kod gönder</button></form>
<form id="f-kod" class="satir" hidden><input id="kod" inputmode="numeric" autocomplete="one-time-code" placeholder="SMS kodu">
<button class="ana" type="submit">Doğrula</button></form>
<div id="recaptcha"></div><p class="durum" id="tel-durum"></p></div>
<div class="kutu" id="eposta-onay" hidden><h2>E-postanızı doğrulayın</h2>
<p class="kucuk">Bağlantı başka bir cihazda açıldı. Güvenlik için bağlantıyı istediğiniz e-postayı yazın.</p>
<form id="f-onay" class="satir"><input type="email" id="onay-eposta" required autocomplete="email">
<button class="ana" type="submit">Giriş yap</button></form><p class="durum" id="onay-durum"></p></div>
<p class="kucuk muted">Giriş yaparak <a href="gizlilik.html">gizlilik ve kişisel verilerin korunması</a> metnini
okuduğunuzu kabul edersiniz.</p>
</section>

<section id="uygulama" hidden>
<div class="sekmeler"><button class="on" data-s="akis">Akış</button><button data-s="takip">Takip ettiklerim</button>
<button data-s="hesap">Hesap</button></div>

<div id="s-akis">
<div class="satir" style="justify-content:space-between"><div class="secim" id="tur">
<button class="on" data-v="">Tümü</button><button data-v="T">Tutanaklar</button><button data-v="O">Oylamalar</button></div>
<label class="kucuk muted"><input type="checkbox" id="sadeceYeni"> Sadece okunmamışlar</label></div>
<div id="liste"></div></div>

<div id="s-takip" hidden>
<div class="kutu"><h2>Milletvekilleri</h2>
<input type="search" id="mv-ara" placeholder="İsim, il veya parti yazın…" autocomplete="off">
<div class="oneri" id="mv-oneri" hidden></div><div class="etiketler" id="mv-liste"></div></div>
<div class="kutu"><h2>Partiler</h2><div class="secim" id="parti-liste"></div></div>
<div class="kutu"><h2>İller</h2><div class="satir"><select id="il-sec"><option value="">İl seçin…</option></select></div>
<div class="etiketler" id="il-liste"></div></div>
<div class="kutu"><h2>Konular ve kelimeler</h2>
<p class="kucuk muted">Tutanak metinlerinin tamamında, özetlerde ve oylanan tekliflerin gerekçelerinde aranır.
Kelimenin başı eşleşir: "emekli" yazarsanız "emekliler", "emeklilik" de bulunur. Birden çok kelime yazarsanız
hepsinin geçtiği kayıtlar gelir.</p>
<form id="f-kelime" class="satir"><input id="kelime" placeholder="ör. asgari ücret, emekli, deprem" maxlength="60">
<button type="submit">Ekle</button></form><div class="etiketler" id="kelime-liste"></div></div>
<p class="durum" id="takip-durum"></p></div>

<div id="s-hesap" hidden>
<div class="kutu"><h2>Hesap</h2><p id="hesap-bilgi"></p>
<div class="satir"><button id="cikis">Çıkış yap</button></div></div>
<div class="kutu"><h2>Hesabı sil</h2>
<p class="kucuk">Hesabınız, takip listeniz ve okundu işaretleriniz kalıcı olarak silinir.</p>
<div class="satir"><button class="tehlike" id="sil">Hesabımı sil</button></div><p class="durum" id="sil-durum"></p></div>
<p class="kucuk"><a href="gizlilik.html">Gizlilik ve kişisel verilerin korunması</a></p>
</div>
</section>
</main>"""
    ayar = {
        "firebase": cfg and {k: cfg[k] for k in ("apiKey", "authDomain", "projectId", "appId") if k in cfg},
        "telefon": bool(cfg and cfg.get("telefon_girisi")),
        "appcheck": cfg and cfg.get("appcheck_recaptcha_enterprise"),
        "surum": surum,
    }
    module = f"""<script>window.AYAR={json.dumps(ayar, ensure_ascii=False)};</script>
<script type="module">{AKIS_JS.replace("__SDK__", FIREBASE_SDK)}</script>"""
    return A.page("Akışım · Meclis Tutanakları", A.TOPBAR_CSS + AKIS_CSS, body + module, "", firebase=True)


AKIS_JS = r"""
// Başka bir sitenin çerçevesi içinde açılmayı reddet (tıklama hırsızlığına karşı)
if (window.top !== window.self) { document.body.innerHTML = ''; window.top.location = location.href; throw new Error('çerçeve'); }
const AY = window.AYAR, $ = id => document.getElementById(id);
const goster = (...ids) => ['yukleniyor','kapali','giris','uygulama','ios-panel'].forEach(i => $(i).hidden = !ids.includes(i));
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const durum = (id, msg, tur='') => { const e = $(id); e.textContent = msg; e.className = 'durum ' + tur; };
if (!AY.firebase) { goster('kapali'); throw new Error('firebase yapılandırılmadı'); }

const SDK = 'https://www.gstatic.com/firebasejs/__SDK__/';
const { initializeApp } = await import(SDK + 'firebase-app.js');
const AU = await import(SDK + 'firebase-auth.js');
const FS = await import(SDK + 'firebase-firestore.js');
const app = initializeApp(AY.firebase);
// App Check: Firebase'e giden her isteğe, gerçekten bu siteden geldiğini kanıtlayan bir reCAPTCHA belgesi ekler
if (AY.appcheck) {
  const AC = await import(SDK + 'firebase-app-check.js');
  AC.initializeAppCheck(app, { provider: new AC.ReCaptchaEnterpriseProvider(AY.appcheck), isTokenAutoRefreshEnabled: true });
}
const auth = AU.getAuth(app); auth.languageCode = 'tr';
const db = FS.getFirestore(app);

// ---------- Giriş: e-posta bağlantısı ----------
const EPOSTA_KEY = 'tbmm-giris-eposta';
const kurulu = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const temizle = () => history.replaceState(null, '', location.pathname);

$('f-eposta').onsubmit = async e => {
  e.preventDefault();
  const eposta = $('eposta').value.trim();
  const url = new URL('akis.html', location.href);
  if (kurulu && ios) url.searchParams.set('uyg', '1');
  try {
    await AU.sendSignInLinkToEmail(auth, eposta, { url: url.href, handleCodeInApp: true });
    try { localStorage.setItem(EPOSTA_KEY, eposta); } catch (_) {}
    durum('eposta-durum', `Giriş bağlantısı ${eposta} adresine gönderildi. E-postadaki bağlantıya dokunun (gelmezse spam klasörüne bakın).`, 'ok');
  } catch (err) { durum('eposta-durum', hataMetni(err), 'hata'); }
};

async function baglantiylaGir(link, eposta) {
  await AU.signInWithEmailLink(auth, eposta, link);
  try { localStorage.removeItem(EPOSTA_KEY); } catch (_) {}
  temizle();
}

$('f-yapistir').onsubmit = async e => {
  e.preventDefault();
  const link = $('link').value.trim();
  if (!AU.isSignInWithEmailLink(auth, link)) { durum('eposta-durum', 'Bu bir giriş bağlantısı değil.', 'hata'); return; }
  let eposta = ''; try { eposta = localStorage.getItem(EPOSTA_KEY) || ''; } catch (_) {}
  if (!eposta) { bekleyenLink = link; goster('giris'); $('eposta-onay').hidden = false; return; }
  try { await baglantiylaGir(link, eposta); } catch (err) { durum('eposta-durum', hataMetni(err), 'hata'); }
};

let bekleyenLink = null;
$('f-onay').onsubmit = async e => {
  e.preventDefault();
  try { await baglantiylaGir(bekleyenLink, $('onay-eposta').value.trim()); $('eposta-onay').hidden = true; }
  catch (err) { durum('onay-durum', hataMetni(err), 'hata'); }
};

function hataMetni(err) {
  const c = err && err.code || '';
  if (c.includes('invalid-email')) return 'E-posta adresi geçersiz.';
  if (c.includes('invalid-action-code') || c.includes('expired-action-code')) return 'Bağlantının süresi dolmuş ya da kullanılmış. Yeni bağlantı isteyin.';
  if (c.includes('too-many-requests') || c.includes('quota')) return 'Çok fazla deneme yapıldı. Biraz sonra tekrar deneyin.';
  if (c.includes('network')) return 'Bağlantı kurulamadı. İnternetinizi kontrol edin.';
  if (c.includes('invalid-phone')) return 'Telefon numarası geçersiz.';
  if (c.includes('invalid-verification-code')) return 'Kod hatalı.';
  return 'Bir hata oluştu (' + (c || err.message) + ').';
}

// ---------- Giriş: telefon (yapılandırmada açılınca görünür) ----------
let onay = null, recaptcha = null;
if (AY.telefon) {
  $('telefon').hidden = false;
  $('f-tel').onsubmit = async e => {
    e.preventDefault();
    const rakam = $('tel').value.replace(/\D/g, '').replace(/^0/, '').replace(/^90/, '');
    if (!/^5\d{9}$/.test(rakam)) { durum('tel-durum', 'Numarayı 5xx xxx xx xx biçiminde yazın.', 'hata'); return; }
    try {
      recaptcha = recaptcha || new AU.RecaptchaVerifier(auth, 'recaptcha', { size: 'invisible' });
      onay = await AU.signInWithPhoneNumber(auth, '+90' + rakam, recaptcha);
      $('f-kod').hidden = false; durum('tel-durum', 'SMS kodu gönderildi.', 'ok');
    } catch (err) { durum('tel-durum', hataMetni(err), 'hata'); }
  };
  $('f-kod').onsubmit = async e => {
    e.preventDefault();
    try { await onay.confirm($('kod').value.trim()); } catch (err) { durum('tel-durum', hataMetni(err), 'hata'); }
  };
}

// ---------- Açılışta: e-postadaki bağlantıyla mı gelindi? ----------
if (AU.isSignInWithEmailLink(auth, location.href)) {
  const istenenUygulama = new URL(location.href).searchParams.get('uyg') === '1';
  if (istenenUygulama && ios && !kurulu) {
    // iPhone: bağlantı uygulamadan istendi ama Safari'de açıldı; uygulamaya taşınması için kopyalat
    goster('ios-panel');
    $('ios-kopyala').onclick = async () => {
      try { await navigator.clipboard.writeText(location.href); durum('ios-durum', 'Kopyalandı. Şimdi uygulamayı açıp yapıştırın.', 'ok'); }
      catch (_) { durum('ios-durum', 'Kopyalanamadı; adres çubuğundaki bağlantıyı elle kopyalayın.', 'hata'); }
    };
    $('ios-burada').onclick = () => girisiTamamla();
  } else {
    girisiTamamla();
  }
}
async function girisiTamamla() {
  let eposta = ''; try { eposta = localStorage.getItem(EPOSTA_KEY) || ''; } catch (_) {}
  if (!eposta) { bekleyenLink = location.href; goster('giris'); $('eposta-onay').hidden = false; return; }
  try { await baglantiylaGir(location.href, eposta); }
  catch (err) { goster('giris'); durum('eposta-durum', hataMetni(err), 'hata'); temizle(); }
}

// ---------- Veriler ----------
const veri = await fetch('veri/akis.json?v=' + AY.surum).then(r => r.json());
const MV = veri.mv, OGE = veri.ogeler;
const mvIndex = Object.fromEntries(MV.map((m, i) => [m[0], i]));
let kullanici = null, takip = { mv: [], parti: [], il: [], kelime: [] };

auth.onAuthStateChanged(async u => {
  kullanici = u;
  if (!u) { if ($('ios-panel').hidden) goster('giris'); $('kim').textContent = ''; return; }
  $('kim').textContent = u.email || u.phoneNumber || '';
  $('hesap-bilgi').textContent = 'Giriş yapılan hesap: ' + (u.email || u.phoneNumber);
  const ref = FS.doc(db, 'users', u.uid);
  const snap = await FS.getDoc(ref);
  if (snap.exists()) {
    takip = Object.assign({ mv: [], parti: [], il: [], kelime: [] }, snap.data().takip || {});
  } else {
    await FS.setDoc(ref, { eposta: u.email || null, telefon: u.phoneNumber || null,
      olusturma: FS.serverTimestamp(), takip });
  }
  goster('uygulama');
  await okunduEsitle();
  takipCiz();
  akisCiz();
});

// ---------- Okundu işaretleri: yerel (sayfalar) + Firestore (cihazlar arası) ----------
const OK_KEY = 'tbmm-okundu';
const yerelOkundu = () => { try { return JSON.parse(localStorage.getItem(OK_KEY) || '{}'); } catch (_) { return {}; } };
async function okunduEsitle() {
  const ref = FS.doc(db, 'users', kullanici.uid, 'veri', 'okundu');
  const uzak = (await FS.getDoc(ref)).data()?.ids || {};
  const yerel = yerelOkundu(), birlesik = { ...uzak };
  for (const [k, t] of Object.entries(yerel)) birlesik[k] = Math.max(birlesik[k] || 0, t);
  try { localStorage.setItem(OK_KEY, JSON.stringify(birlesik)); } catch (_) {}
  if (Object.keys(birlesik).length !== Object.keys(uzak).length)
    await FS.setDoc(ref, { ids: birlesik, guncelleme: FS.serverTimestamp() });
}

// ---------- Takip ettiklerim ----------
let kayitZamani;
function kaydet() {
  clearTimeout(kayitZamani);
  kayitZamani = setTimeout(async () => {
    try {
      await FS.updateDoc(FS.doc(db, 'users', kullanici.uid), { takip, guncelleme: FS.serverTimestamp() });
      durum('takip-durum', 'Kaydedildi.', 'ok');
    } catch (err) { durum('takip-durum', 'Kaydedilemedi: ' + hataMetni(err), 'hata'); }
  }, 400);
  akisCiz();
}
function etiketler(el, liste, ad, yaz) {
  $(el).innerHTML = liste.map((x, i) => `<span class="etiket">${esc(yaz(x))}<button data-i="${i}" title="Kaldır">×</button></span>`).join('')
    || '<span class="kucuk muted">Henüz yok.</span>';
  $(el).querySelectorAll('button').forEach(b => b.onclick = () => { takip[ad].splice(+b.dataset.i, 1); takipCiz(); kaydet(); });
}
const mvYaz = id => { const m = MV[mvIndex[id]]; return m ? `${m[1]} · ${m[2]} · ${m[3]}` : id; };
function takipCiz() {
  etiketler('mv-liste', takip.mv, 'mv', mvYaz);
  etiketler('il-liste', takip.il, 'il', x => x);
  etiketler('kelime-liste', takip.kelime, 'kelime', x => '“' + x + '”');
  $('parti-liste').innerHTML = veri.partiler.map(p => `<button class="${takip.parti.includes(p) ? 'on' : ''}" data-p="${esc(p)}">${esc(p)}</button>`).join('');
  $('parti-liste').querySelectorAll('button').forEach(b => b.onclick = () => {
    const p = b.dataset.p, i = takip.parti.indexOf(p);
    i < 0 ? takip.parti.push(p) : takip.parti.splice(i, 1); takipCiz(); kaydet();
  });
}
const kucuk = s => s.replace(/I/g, 'ı').replace(/İ/g, 'i').toLocaleLowerCase('tr');
$('mv-ara').oninput = () => {
  const q = kucuk($('mv-ara').value.trim());
  if (q.length < 2) { $('mv-oneri').hidden = true; return; }
  const sonuc = MV.filter(m => kucuk(m[1] + ' ' + m[2] + ' ' + m[3]).includes(q) && !takip.mv.includes(m[0])).slice(0, 12);
  $('mv-oneri').innerHTML = sonuc.map(m => `<button data-id="${esc(m[0])}">${esc(m[1])} <small>${esc(m[2])} · ${esc(m[3])}</small></button>`).join('')
    || '<p class="kucuk muted" style="padding:8px 12px;margin:0">Bulunamadı.</p>';
  $('mv-oneri').hidden = false;
  $('mv-oneri').querySelectorAll('button').forEach(b => b.onclick = () => {
    takip.mv.push(b.dataset.id); $('mv-ara').value = ''; $('mv-oneri').hidden = true; takipCiz(); kaydet();
  });
};
$('il-sec').innerHTML += veri.iller.map(il => `<option>${esc(il)}</option>`).join('');
$('il-sec').onchange = () => {
  const il = $('il-sec').value; $('il-sec').value = '';
  if (il && !takip.il.includes(il)) { takip.il.push(il); takipCiz(); kaydet(); }
};
$('f-kelime').onsubmit = e => {
  e.preventDefault();
  const k = $('kelime').value.trim().replace(/\s+/g, ' ');
  if (k.length < 3) { durum('takip-durum', 'En az 3 harf yazın.', 'hata'); return; }
  if (!takip.kelime.includes(k) && takip.kelime.length < 50) { takip.kelime.push(k); takipCiz(); kaydet(); }
  $('kelime').value = '';
};

// ---------- Kelime dizini ----------
const norm = s => s.replace(/I/g, 'ı').replace(/İ/g, 'i').toLocaleLowerCase('tr').replace(/â/g, 'a').replace(/î/g, 'i').replace(/û/g, 'u');
const ASCII = { 'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u' };
const parcalar = {};
const parcaYukle = k => parcalar[k] ||= fetch(`veri/kelime/${k}.json?v=${AY.surum}`).then(r => r.ok ? r.json() : {}).catch(() => ({}));
async function kelimeEsles(kelime) {
  const ws = (norm(kelime).match(/[a-zçğıöşü0-9]+/g) || []).filter(w => w.length >= 3);
  let sonuc = null;
  for (const w of ws) {
    const p = await parcaYukle([...w.slice(0, 2)].map(c => ASCII[c] || c).join(''));
    const s = new Set();
    for (const [tok, ids] of Object.entries(p)) if (tok.startsWith(w)) ids.forEach(i => s.add(i));
    sonuc = sonuc ? new Set([...sonuc].filter(x => s.has(x))) : s;
  }
  return sonuc || new Set();
}

// ---------- Akış ----------
const OYLAR = { K: 'Kabul', R: 'Ret', C: 'Çekimser', X: 'Katılmadı' };
const dagilim = a => ['kabul', 'ret', 'çekimser', 'katılmadı'].map((l, i) => a[i] ? a[i] + ' ' + l : '').filter(Boolean).join(' · ');
const AYLAR = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
const GUNLER = ['Pazar','Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi'];
const gunYaz = d => { const t = new Date(d + 'T12:00:00'); return `${t.getDate()} ${AYLAR[t.getMonth()]} ${t.getFullYear()} ${GUNLER[t.getDay()]}`; };
let tur = '', ciziliyor = 0;

async function akisCiz() {
  const benim = ++ciziliyor;
  const bos = !takip.mv.length && !takip.parti.length && !takip.il.length && !takip.kelime.length;
  if (bos) { $('liste').innerHTML = '<p class="bos">Akışınız boş. <b>Takip ettiklerim</b> sekmesinden milletvekili, parti, il veya konu ekleyin.</p>'; return; }
  const kelimeEs = {};
  for (const k of takip.kelime) kelimeEs[k] = await kelimeEsles(k);
  if (benim !== ciziliyor) return;
  const okunan = yerelOkundu(), sadeceYeni = $('sadeceYeni').checked;
  const satirlar = [];
  OGE.forEach((o, idx) => {
    if (tur && o.t !== tur) return;
    const neden = [];
    for (const id of takip.mv) {
      const i = mvIndex[id]; if (i === undefined) continue;
      const ad = MV[i][1];
      if (o.t === 'T' && o.k[i]) neden.push(`<a href="${o.p}#konusmaci=${esc(o.k[i][1])}">${esc(ad)} konuştu (${o.k[i][0]})</a>`);
      if (o.t === 'O' && o.v[i] && o.v[i] !== '-') neden.push(`${esc(ad)}: <b>${OYLAR[o.v[i]]}</b>`);
    }
    for (const p of takip.parti) {
      if (o.t === 'T' && o.pk[p]) neden.push(`${esc(p)}: ${o.pk[p]} konuşmacı`);
      if (o.t === 'O' && o.pv[p]) neden.push(`${esc(p)}: ${dagilim(o.pv[p])}`);
    }
    for (const il of takip.il) {
      if (o.t === 'T' && o.ik[il]) neden.push(`${esc(il)}: ${o.ik[il]} konuşmacı`);
      if (o.t === 'O' && o.iv[il]) neden.push(`${esc(il)}: ${dagilim(o.iv[il])}`);
    }
    for (const k of takip.kelime) if (kelimeEs[k].has(idx)) neden.push(`“${esc(k)}” geçiyor`);
    if (!neden.length) return;
    const yeni = !okunan[o.id];
    if (sadeceYeni && !yeni) return;
    satirlar.push({ o, neden, yeni });
  });
  satirlar.reverse();
  let html = '', gun = '';
  for (const { o, neden, yeni } of satirlar.slice(0, 300)) {
    if (o.d !== gun) { gun = o.d; html += `<h3 class="gun">${gunYaz(o.d)}</h3>`; }
    const pill = o.t === 'O'
      ? `<span class="pill oy">Oylama</span>${o.s ? `<span class="muted kucuk">${o.s}</span>` : ''}<span class="pill ${/edilme|redd/i.test(o.so) ? 'red' : 'ok'}">${esc(o.so || '')}</span>`
      : `<span class="pill ${/^bas/i.test(o.du) ? 'basilmis' : /^tam/i.test(o.du) ? 'tam' : 'ham'}">${esc(o.du)}</span>`;
    html += `<div class="kart ${yeni ? 'unread' : ''}"><a href="${o.p}" style="text-decoration:none;display:block">
      <div class="r1">${pill}<span class="b">${esc(o.b)}</span>${yeni ? '<span class="pill yeni">Yeni</span>' : ''}</div>
      ${o.l ? `<div class="l">${esc(o.l)}</div>` : ''}</a><div class="neden">${neden.map(n => `<span>${n}</span>`).join('')}</div></div>`;
  }
  $('liste').innerHTML = html || '<p class="bos">Takip ettiklerinizle eşleşen kayıt yok.</p>';
}
$('tur').querySelectorAll('button').forEach(b => b.onclick = () => {
  tur = b.dataset.v; $('tur').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); akisCiz();
});
$('sadeceYeni').onchange = akisCiz;
addEventListener('pageshow', e => { if (e.persisted && kullanici) akisCiz(); });

// ---------- Sekmeler ----------
document.querySelectorAll('.sekmeler button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.sekmeler button').forEach(x => x.classList.toggle('on', x === b));
  ['akis', 'takip', 'hesap'].forEach(s => $('s-' + s).hidden = s !== b.dataset.s);
});

// ---------- Hesap ----------
$('cikis').onclick = async () => {
  await AU.signOut(auth);
  try { localStorage.removeItem(EPOSTA_KEY); } catch (_) {}
};
$('sil').onclick = async () => {
  const son = Date.parse(kullanici.metadata.lastSignInTime || 0);
  if (Date.now() - son > 5 * 60 * 1000) {
    durum('sil-durum', 'Güvenlik için hesabı silmeden önce çıkış yapıp yeniden giriş yapın, sonra tekrar deneyin.', 'hata'); return;
  }
  if (!confirm('Hesabınız ve tüm verileriniz kalıcı olarak silinecek. Emin misiniz?')) return;
  try {
    await FS.deleteDoc(FS.doc(db, 'users', kullanici.uid, 'veri', 'okundu'));
    await FS.deleteDoc(FS.doc(db, 'users', kullanici.uid));
    await AU.deleteUser(kullanici);
    try { localStorage.removeItem(OK_KEY); } catch (_) {}
    alert('Hesabınız silindi.');
  } catch (err) { durum('sil-durum', hataMetni(err), 'hata'); }
};
"""


def build_gizlilik_page() -> str:
    body = """<div class="top"><div class="bar-in"><a class="home" href="index.html">← <b>Tüm kayıtlar</b></a></div></div>
<main class="wrap"><h1>Gizlilik ve kişisel verilerin korunması</h1>
<div class="kutu"><p><b>Taslak.</b> Bu metin, uygulamanın teknik olarak hangi verileri işlediğini açıklar; yayın
öncesinde KVKK kapsamındaki aydınlatma metniyle değiştirilecektir.</p></div>
<div class="kutu"><h2>Hesap açmadan</h2><p>Siteyi okumak için hesap gerekmez. Okundu işaretleri yalnızca kendi
tarayıcınızda tutulur.</p></div>
<div class="kutu"><h2>Hesap açtığınızda tutulanlar</h2><ul>
<li>Giriş için kullandığınız e-posta adresi (ya da telefon numarası)</li>
<li>Takip ettiğiniz milletvekilleri, partiler, iller ve kelimeler</li>
<li>Okuduğunuz tutanak ve oylamaların listesi (cihazlarınız arasında eşitlemek için)</li></ul>
<p>Bu veriler Google Firebase (Authentication ve Cloud Firestore) üzerinde saklanır; yalnızca siz
erişebilirsiniz.</p></div>
<div class="kutu"><h2>Silme</h2><p><b>Akışım → Hesap → Hesabımı sil</b> ile hesabınızı ve tüm verilerinizi
istediğiniz zaman kalıcı olarak silebilirsiniz.</p></div>
<div class="kutu"><h2>Kaynak</h2><p>Tutanak ve oylama içerikleri TBMM'nin kamuya açık yayınlarından alınır.</p></div>
</main>"""
    return A.page("Gizlilik · Meclis Tutanakları", A.TOPBAR_CSS + AKIS_CSS, body, "")


def build(sessions: list[dict], votes: list[dict], out: Path) -> list[str]:
    surum = build_data(sessions, votes, out)
    (out / "akis.html").write_text(build_akis_page(firebase_config(), surum), encoding="utf-8")
    (out / "gizlilik.html").write_text(build_gizlilik_page(), encoding="utf-8")
    return ["akis.html", "gizlilik.html"]
