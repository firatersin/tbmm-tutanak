// Canlı Firestore kurallarını iki geçici test hesabıyla dener; sonunda hesapları ve belgeleri siler.
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const FT = path.join(process.env.APPDATA, "npm", "node_modules", "firebase-tools", "lib");
const { requireAuth } = require(path.join(FT, "requireAuth"));
const { Client } = require(path.join(FT, "apiv2"));
const P = "meclis-ce5d2";
const KEY = JSON.parse(fs.readFileSync(process.argv[2], "utf8")).apiKey;
const REF = { Referer: "https://firatersin.github.io/" };
const DB = `https://firestore.googleapis.com/v1/projects/${P}/databases/(default)/documents`;
const admin = new Client({ urlPrefix: "https://identitytoolkit.googleapis.com", auth: true });

let gecti = 0, kaldi = 0;
function sonuc(ad, beklenen, durum) {
  const izin = durum >= 200 && durum < 300;
  const ok = izin === (beklenen === "İZİN");
  ok ? gecti++ : kaldi++;
  console.log(`${ok ? "✓" : "✗ HATA"}  ${ad.padEnd(62)} beklenen ${beklenen.padEnd(5)} | sonuç ${izin ? "İZİN" : "RET"} (${durum})`);
}
async function istek(token, method, url, body) {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) },
    body: body ? JSON.stringify(body) : undefined });
  return r.status;
}
const str = (s) => ({ stringValue: s }), nul = { nullValue: null };
const arr = (a) => ({ arrayValue: { values: a.map(str) } });
const takip = (mv = []) => ({ mapValue: { fields: { mv: arr(mv), parti: arr([]), il: arr([]), kelime: arr([]) } } });
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
    { method: "POST", headers: { "Content-Type": "application/json", ...REF }, body: JSON.stringify({ email, password: sifre, returnSecureToken: true }) });
  const j = await r.json();
  if (!j.idToken) throw new Error("giriş başarısız: " + JSON.stringify(j.error));
  return { uid: u.localId, email, token: j.idToken };
}

(async () => {
  const h = require(path.join(FT, "auth")).getGlobalDefaultAccount();
  await requireAuth({ project: P, user: h.user, tokens: h.tokens });
  const A = await kullanici("kural-testi-a@example.com", true);
  const B = await kullanici("kural-testi-b@example.com", false);
  const temel = (k) => ({ eposta: str(k.email), telefon: nul, takip: takip() });
  try {
    sonuc("Doğrulanmamış hesap kendi belgesini oluşturur", "RET", await yaz(B.token, `users/${B.uid}`, temel(B), { zaman: ["olusturma"], varMi: false }));
    sonuc("Başkasının uid'iyle belge oluşturma", "RET", await yaz(A.token, `users/${B.uid}`, temel(A), { zaman: ["olusturma"], varMi: false }));
    sonuc("Başkasının e-postasını yazarak oluşturma", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), eposta: str("baskasi@example.com") }, { zaman: ["olusturma"], varMi: false }));
    sonuc("Fazladan alan ('yonetici') ekleyerek oluşturma", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), yonetici: { booleanValue: true } }, { zaman: ["olusturma"], varMi: false }));
    sonuc("İstemcinin uydurduğu oluşturma zamanıyla oluşturma", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), olusturma: { timestampValue: "2020-01-01T00:00:00Z" } }, { varMi: false }));
    sonuc("Geçerli: kendi belgesini oluşturma", "İZİN", await yaz(A.token, `users/${A.uid}`, temel(A), { zaman: ["olusturma"], varMi: false }));
    sonuc("Kendi belgesini okuma", "İZİN", await istek(A.token, "GET", `${DB}/users/${A.uid}`));
    sonuc("users koleksiyonunu listeleme", "RET", await istek(A.token, "GET", `${DB}/users`));
    sonuc("Başkasının belgesini okuma (doğrulanmamış B, A'nınkini)", "RET", await istek(B.token, "GET", `${DB}/users/${A.uid}`));
    sonuc("Giriş yapmadan okuma", "RET", await istek(null, "GET", `${DB}/users/${A.uid}`));
    sonuc("Geçerli: takip listesini güncelleme", "İZİN", await yaz(A.token, `users/${A.uid}`, { ...temel(A), takip: takip(["x--y"]) }, { zaman: ["olusturma", "guncelleme"] }).then(async () =>
      // olusturma alanı sabit kalmalı: mevcut değeri okuyup aynısını gönder
      { const d = await (await fetch(`${DB}/users/${A.uid}`, { headers: { Authorization: "Bearer " + A.token } })).json();
        return yaz(A.token, `users/${A.uid}`, { ...temel(A), olusturma: d.fields.olusturma, takip: takip(["a--b"]) }, { zaman: ["guncelleme"] }); }));
    const d = await (await fetch(`${DB}/users/${A.uid}`, { headers: { Authorization: "Bearer " + A.token } })).json();
    sonuc("E-postayı değiştirerek güncelleme", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), olusturma: d.fields.olusturma, eposta: str("yeni@example.com") }, { zaman: ["guncelleme"] }));
    sonuc("Sunucu zamanı olmadan güncelleme", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), olusturma: d.fields.olusturma }));
    sonuc("Sınırı aşan takip listesi (301 milletvekili)", "RET", await yaz(A.token, `users/${A.uid}`, { ...temel(A), olusturma: d.fields.olusturma, takip: takip(Array.from({ length: 301 }, (_, i) => "m" + i)) }, { zaman: ["guncelleme"] }));
    sonuc("Geçerli: okundu işaretlerini yazma", "İZİN", await yaz(A.token, `users/${A.uid}/veri/okundu`, { ids: { mapValue: { fields: { "28-5-4:ham": { integerValue: "1" } } } } }, { zaman: ["guncelleme"] }));
    sonuc("veri altında başka belge adı", "RET", await yaz(A.token, `users/${A.uid}/veri/baska`, { ids: { mapValue: { fields: {} } } }, { zaman: ["guncelleme"] }));
    sonuc("Başka bir koleksiyona yazma", "RET", await yaz(A.token, `baska/${A.uid}`, { a: str("b") }));
    sonuc("Başkasının okundu belgesine yazma", "RET", await yaz(B.token, `users/${A.uid}/veri/okundu`, { ids: { mapValue: { fields: {} } } }, { zaman: ["guncelleme"] }));
    sonuc("Geçerli: kendi verilerini silme", "İZİN", (await istek(A.token, "DELETE", `${DB}/users/${A.uid}/veri/okundu`), await istek(A.token, "DELETE", `${DB}/users/${A.uid}`)));
  } finally {
    for (const k of [A, B]) await admin.post(`/v1/projects/${P}/accounts:delete`, { localId: k.uid });
    const kalan = (await admin.post(`/v1/projects/${P}/accounts:query`, { returnUserInfo: true })).body;
    console.log(`\n${gecti} geçti, ${kaldi} kaldı. Test hesapları silindi; kalan kullanıcı: ${kalan.recordsCount || 0}`);
  }
})().catch((e) => { console.error("HATA:", e.message.split("\n")[0]); process.exit(1); });
