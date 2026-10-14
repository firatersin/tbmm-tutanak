// App Check zorunluluğunu kanıtlar: aynı istek geçerli App Check belgesiyle geçmeli, belgesiz reddedilmeli.
// Geçici bir hata ayıklama belgesi ve geçici bir test hesabı kullanır; sonunda ikisini de siler.
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
const c = (u) => new Client({ urlPrefix: u, auth: true });

let gecti = 0, kaldi = 0;
const sonuc = (ad, beklenen, durum, mesaj = "") => {
  const izin = durum >= 200 && durum < 300, ok = izin === (beklenen === "İZİN");
  ok ? gecti++ : kaldi++;
  console.log(`${ok ? "✓" : "✗ HATA"}  ${ad.padEnd(58)} beklenen ${beklenen.padEnd(5)} | sonuç ${izin ? "İZİN" : "RET"} (${durum}) ${mesaj}`);
};

(async () => {
  const h = require(path.join(FT, "auth")).getGlobalDefaultAccount();
  await requireAuth({ project: P, user: h.user, tokens: h.tokens });
  const ac = c("https://firebaseappcheck.googleapis.com"), it = c("https://identitytoolkit.googleapis.com");
  const debug = crypto.randomUUID();
  const dt = (await ac.post(`/v1/projects/${N}/apps/${APP}/debugTokens`, { displayName: "gecici-test", token: debug })).body;
  let uid;
  try {
    const ex = await (await fetch(`https://firebaseappcheck.googleapis.com/v1/projects/${N}/apps/${APP}:exchangeDebugToken?key=${KEY}`,
      { method: "POST", headers: REF, body: JSON.stringify({ debugToken: debug }) })).json();
    const AC = { "X-Firebase-AppCheck": ex.token };
    const email = "appcheck-testi@example.com", sifre = crypto.randomBytes(18).toString("base64");
    uid = (await it.post(`/v1/projects/${P}/accounts`, { email, password: sifre, emailVerified: true })).body.localId;

    const giris = (ek) => fetch(`https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${KEY}`,
      { method: "POST", headers: { ...REF, ...ek }, body: JSON.stringify({ email, password: sifre, returnSecureToken: true }) });
    let r = await giris({});
    sonuc("Giriş, App Check belgesi olmadan", "RET", r.status, (await r.json()).error?.message || "");
    r = await giris(AC);
    const j = await r.json();
    sonuc("Giriş, geçerli App Check belgesiyle", "İZİN", r.status);
    const ID = { Authorization: "Bearer " + j.idToken, "Content-Type": "application/json" };

    const yaz = (ek) => fetch(`${DB}:commit`, { method: "POST", headers: { ...ID, ...ek }, body: JSON.stringify({ writes: [{
      update: { name: `projects/${P}/databases/(default)/documents/users/${uid}`,
        fields: { eposta: { stringValue: email }, telefon: { nullValue: null }, takip: { mapValue: { fields: {} } } } },
      updateTransforms: [{ fieldPath: "olusturma", setToServerValue: "REQUEST_TIME" }], currentDocument: { exists: false } }] }) });
    r = await yaz({});
    sonuc("Firestore yazma, giriş var ama App Check yok", "RET", r.status, (await r.json()).error?.message || "");
    r = await yaz(AC);
    sonuc("Firestore yazma, giriş + App Check", "İZİN", r.status);
    r = await fetch(`${DB}/users/${uid}`, { headers: ID });
    sonuc("Firestore okuma, giriş var ama App Check yok", "RET", r.status, (await r.json()).error?.message || "");
    r = await fetch(`${DB}/users/${uid}`, { headers: { ...ID, ...AC } });
    sonuc("Firestore okuma, giriş + App Check", "İZİN", r.status);
    await fetch(`${DB}/users/${uid}`, { method: "DELETE", headers: { ...ID, ...AC } });
  } finally {
    if (uid) await it.post(`/v1/projects/${P}/accounts:delete`, { localId: uid });
    await ac.delete(`/v1/${dt.name}`);
    const kalanDebug = (await ac.get(`/v1/projects/${N}/apps/${APP}/debugTokens`)).body.debugTokens || [];
    const kalan = (await it.post(`/v1/projects/${P}/accounts:query`, {})).body.recordsCount || 0;
    console.log(`\n${gecti} geçti, ${kaldi} kaldı. Temizlik: kalan kullanıcı ${kalan}, kalan hata ayıklama belgesi ${kalanDebug.length}`);
  }
})().catch((e) => { console.error("HATA:", e.message.split("\n")[0]); process.exit(1); });
