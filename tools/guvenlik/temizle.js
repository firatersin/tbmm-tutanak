// Testlerden kalan App Check hata ayıklama belgelerini, test kullanıcılarını ve belgelerini siler.
const path = require("path");
const FT = path.join(process.env.APPDATA, "npm", "node_modules", "firebase-tools", "lib");
const { requireAuth } = require(path.join(FT, "requireAuth"));
const { Client } = require(path.join(FT, "apiv2"));
const P = "meclis-ce5d2", N = "683559903563", APP = "1:683559903563:web:6efd0eea408082b96188ce";
const c = (u) => new Client({ urlPrefix: u, auth: true });

(async () => {
  const h = require(path.join(FT, "auth")).getGlobalDefaultAccount();
  await requireAuth({ project: P, user: h.user, tokens: h.tokens });
  const ac = c("https://firebaseappcheck.googleapis.com"), it = c("https://identitytoolkit.googleapis.com");

  const liste = async () => (await ac.get(`/v1/projects/${N}/apps/${APP}/debugTokens`)).body.debugTokens || [];
  for (const t of await liste()) {
    await ac.delete(`/v1/${t.name}`);
    console.log("Silinen hata ayıklama belgesi:", t.displayName);
  }
  console.log("Kalan hata ayıklama belgesi:", (await liste()).length);

  const users = (await it.post(`/v1/projects/${P}/accounts:query`, { returnUserInfo: true })).body.userInfo || [];
  for (const u of users.filter((u) => (u.email || "").endsWith("@example.com"))) {
    await it.post(`/v1/projects/${P}/accounts:delete`, { localId: u.localId });
    console.log("Silinen test kullanıcısı:", u.email);
  }
  console.log("Kalan kullanıcı:", (await it.post(`/v1/projects/${P}/accounts:query`, {})).body.recordsCount || 0);

  const fs = c("https://firestore.googleapis.com");
  const docs = (await fs.get(`/v1/projects/${P}/databases/(default)/documents/users`, { queryParams: { pageSize: 100 } })).body.documents || [];
  for (const d of docs) {
    await fs.delete(`/v1/${d.name}/veri/okundu`).catch(() => {});
    await fs.delete(`/v1/${d.name}`);
    console.log("Silinen test belgesi:", d.name.split("/").pop());
  }
  console.log("Kalan users belgesi:", ((await fs.get(`/v1/projects/${P}/databases/(default)/documents/users`)).body.documents || []).length);
})().catch((e) => { console.error("HATA:", e.message.split("\n")[0]); process.exit(1); });
