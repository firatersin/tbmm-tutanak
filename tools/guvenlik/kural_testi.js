// Canlı Firestore kurallarını iki geçici test hesabıyla dener; sonunda hesapları, belgeleri ve geçici
// App Check hata ayıklama belgesini siler. App Check zorunlu olduğu için istekler geçerli bir App Check belgesi taşır.
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const FT = path.join(process.env.APPDATA, "npm", "node_modules", "firebase-tools", "lib");
const { requireAuth } = require(path.join(FT, "requireAuth"));
const { Client } = require(path.join(FT, "apiv2"));
const P = "meclis-ce5d2", N = "683559903563", APP = "1:683559903563:web:6efd0eea408082b96188ce";
const KEY = JSON.parse(fs.readFileSync(process.argv[2], "utf8")).apiKey;
const REF = { Referer: "https://firatersin.github.io/", "Content-Type": "application/json" };
const DB = `https://firestore.googleapis.com/v1/projects/${P}/databases/(default)/documents`;
const admin = new Client({ urlPrefix: "https://identitytoolkit.googleapis.com", auth: true });
const ac = new Client({ urlPrefix: "https://firebaseappcheck.googleapis.com", auth: true });
let AC = {};

let gecti = 0, kaldi = 0;
function sonuc(ad, beklenen, durum) {
  const izin = durum >= 200 && durum < 300;
  const ok = izin === (beklenen === "İZİN");
  ok ? gecti++ : kaldi++;
  console.log(`${ok ? "✓" : "✗ HATA"}  ${ad.padEnd(62)} beklenen ${beklenen.padEnd(5)} | sonuç ${izin ? "İZİN" : "RET"} (${durum})`);
}
async function istek(token, method, url, body) {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json", ...AC, ...(token ? { Authorization: "Bearer " + token } : {}) },
    body: body ? JSON.stringify(body) : undefined });
  return r.status;
}
const oku = async (token, yol) => (await fetch(`${DB}/${yol}`, { headers: { ...AC, Authorization: "Bearer " + token } })).json();
const str = (s) => ({ stringValue: s }), nul = { nullValue: null }, bool = (b) => ({ booleanValue: b });
const arr = (a) => ({ arrayValue: { values: a.map(str) } });
const harita = (o) => ({ mapValue: { fields: o } });
const takip = (mv = []) => harita({ mv: arr(mv), parti: arr([]), iller: arr(["İzmir"]), kelime: arr([]), konular: arr(["afet"]) });
const tercih = (ritim = "gunluk") => harita({ turler: harita({ oylama: bool(true), ozet: bool(true), konusma: bool(false), teklif: bool(false) }),
  ritim: str(ritim), sessiz: harita({ bas: str("23:00"), bit: str("08:00") }) });
const riza = harita({ metin: str("acik-riza-v1-2026-10") });
// Belge yazma (commit) — sunucu zamanı için alan dönüşümü kullanılır
function yaz(token, docPath, fields, { zaman = [], varMi } = {}) {
  const w = { update: { name: `projects/${P}/databases/(default)/documents/${docPath}`, fields },
    updateTransforms: zaman.map((f) => ({ fieldPath: f, setToServerValue: "REQUEST_TIME" })) };
  if (varMi !== undefined) w.currentDocument = { exists: varMi };
  return istek(token, "POST", `${DB}:commit`, { writes: [w] });
}

async function kullanici(email, dogrulanmis) {
  const sifre = crypto.randomBytes(18).toString("base64");
  const u = (await admin.post(`/v1/projects/${P}/accounts`, { email, password: sifre, emailVerified: dogrulanmis })).body;
  const r = await fetch(`https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${KEY}`,
    { method: "POST", headers: { ...REF, ...AC }, body: JSON.stringify({ email, password: sifre, returnSecureToken: true }) });
  const j = await r.json();
  if (!j.idToken) throw new Error("giriş başarısız: " + JSON.stringify(j.error));
  return { uid: u.localId, email, token: j.idToken };
}

(async () => {
  const h = require(path.join(FT, "auth")).getGlobalDefaultAccount();
  await requireAuth({ project: P, user: h.user, tokens: h.tokens });
  const debug = crypto.randomUUID();
  const dt = (await ac.post(`/v1/projects/${N}/apps/${APP}/debugTokens`, { displayName: "gecici-kural-testi", token: debug })).body;
  const kullanicilar = [];
  try {
    const ex = await (await fetch(`https://firebaseappcheck.googleapis.com/v1/projects/${N}/apps/${APP}:exchangeDebugToken?key=${KEY}`,
      { method: "POST", headers: REF, body: JSON.stringify({ debugToken: debug }) })).json();
    AC = { "X-Firebase-AppCheck": ex.token };
    const A = await kullanici("kural-testi-a@example.com", true); kullanicilar.push(A);
    const B = await kullanici("kural-testi-b@example.com", false); kullanicilar.push(B);
    const temel = (k) => ({ eposta: str(k.email), telefon: nul, takip: takip(), tercih: tercih(), riza });
    const olustur = ["olusturma", "riza.zaman"];

    sonuc("Doğrulanmamış hesap kendi belgesini oluşturur", "RET", await yaz(B.token, `users/${B.uid}`, temel(B), { zaman: olustur, varMi: false }));
    sonuc("Başkasının uid'iyle belge oluşturma", "RET", await yaz(A.token, `users/${B.uid}`, temel(A), { zaman: olustur, varMi: false }));
    sonuc("Başkasının e-postasını yazarak oluşturma", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), eposta: str("baskasi@example.com") }, { zaman: olustur, varMi: false }));
    sonuc("Fazladan alan ('yonetici') ekleyerek oluşturma", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), yonetici: bool(true) }, { zaman: olustur, varMi: false }));
    sonuc("İstemcinin uydurduğu oluşturma zamanıyla oluşturma", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), olusturma: { timestampValue: "2020-01-01T00:00:00Z" } }, { zaman: ["riza.zaman"], varMi: false }));
    const rizasiz = temel(A); delete rizasiz.riza;
    sonuc("Açık rıza kaydı olmadan oluşturma", "RET", await yaz(A.token, `users/${A.uid}`, rizasiz, { zaman: ["olusturma"], varMi: false }));
    sonuc("Geçersiz sıklık değeriyle oluşturma", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), tercih: tercih("her-dakika") }, { zaman: olustur, varMi: false }));
    sonuc("Geçerli: rızayla kendi belgesini oluşturma", "İZİN", await yaz(A.token, `users/${A.uid}`, temel(A), { zaman: olustur, varMi: false }));
    sonuc("Kendi belgesini okuma", "İZİN", await istek(A.token, "GET", `${DB}/users/${A.uid}`));
    sonuc("users koleksiyonunu listeleme", "RET", await istek(A.token, "GET", `${DB}/users`));
    sonuc("Başkasının belgesini okuma (doğrulanmamış B, A'nınkini)", "RET", await istek(B.token, "GET", `${DB}/users/${A.uid}`));
    sonuc("Giriş yapmadan okuma", "RET", await istek(null, "GET", `${DB}/users/${A.uid}`));
    const d = await oku(A.token, `users/${A.uid}`);
    const sabit = { olusturma: d.fields.olusturma, riza: d.fields.riza };
    sonuc("Geçerli: takip listesini ve planı güncelleme", "İZİN", await yaz(A.token, `users/${A.uid}`, { ...temel(A), ...sabit, takip: takip(["a--b"]), tercih: tercih("haftalik") }, { zaman: ["guncelleme"] }));
    sonuc("E-postayı değiştirerek güncelleme", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), ...sabit, eposta: str("yeni@example.com") }, { zaman: ["guncelleme"] }));
    sonuc("Rıza kaydını değiştirerek güncelleme", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), olusturma: sabit.olusturma, riza: harita({ metin: str("baska"), zaman: { timestampValue: "2020-01-01T00:00:00Z" } }) }, { zaman: ["guncelleme"] }));
    sonuc("Sunucu zamanı olmadan güncelleme", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), ...sabit }));
    sonuc("Sınırı aşan takip listesi (301 milletvekili)", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), ...sabit, takip: takip(Array.from({ length: 301 }, (_, i) => "m" + i)) }, { zaman: ["guncelleme"] }));
    sonuc("Geçerli: okundu işaretlerini yazma", "İZİN", await yaz(A.token, `users/${A.uid}/veri/okundu`, { ids: harita({ "28-5-4:ham": { integerValue: "1" } }) }, { zaman: ["guncelleme"] }));
    sonuc("veri altında başka belge adı", "RET", await yaz(A.token, `users/${A.uid}/veri/baska`, { ids: harita({}) }, { zaman: ["guncelleme"] }));
    sonuc("Başka bir koleksiyona yazma", "RET", await yaz(A.token, `baska/${A.uid}`, { a: str("b") }));
    sonuc("Başkasının okundu belgesine yazma", "RET", await yaz(B.token, `users/${A.uid}/veri/okundu`, { ids: harita({}) }, { zaman: ["guncelleme"] }));
    sonuc("Geçerli: kendi verilerini silme", "İZİN", (await istek(A.token, "DELETE", `${DB}/users/${A.uid}/veri/okundu`), await istek(A.token, "DELETE", `${DB}/users/${A.uid}`)));
  } finally {
    for (const k of kullanicilar) await admin.post(`/v1/projects/${P}/accounts:delete`, { localId: k.uid });
    await ac.delete(`/v1/${dt.name}`);
    const kalan = (await admin.post(`/v1/projects/${P}/accounts:query`, { returnUserInfo: true })).body;
    const kalanDebug = (await ac.get(`/v1/projects/${N}/apps/${APP}/debugTokens`)).body.debugTokens || [];
    console.log(`\n${gecti} geçti, ${kaldi} kaldı. Temizlik: kalan kullanıcı ${kalan.recordsCount || 0}, kalan hata ayıklama belgesi ${kalanDebug.length}`);
  }
})().catch((e) => { console.error("HATA:", e.message.split("\n")[0]); process.exit(1); });
