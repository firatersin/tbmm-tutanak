// Salt okunur güvenlik denetimi: Auth ayarları, API anahtarları, IAM, faturalandırma, RTDB/Storage, Firestore.
const path = require("path");
const FT = path.join(process.env.APPDATA, "npm", "node_modules", "firebase-tools", "lib");
const { requireAuth } = require(path.join(FT, "requireAuth"));
const { Client } = require(path.join(FT, "apiv2"));
const P = "meclis-ce5d2", N = "683559903563";

const c = (u) => new Client({ urlPrefix: u, auth: true });
const dene = async (ad, fn) => { try { console.log(ad + ":", await fn()); } catch (e) { console.log(ad + ": HATA", (e.status || ""), e.message.split("\n")[0]); } };

(async () => {
  const h = require(path.join(FT, "auth")).getGlobalDefaultAccount();
  await requireAuth({ project: P, user: h.user, tokens: h.tokens });

  await dene("Auth yapılandırması", async () => {
    const r = (await c("https://identitytoolkit.googleapis.com").get(`/admin/v2/projects/${P}/config`)).body;
    return JSON.stringify({
      signIn: r.signIn && { email: r.signIn.email, phoneNumber: r.signIn.phoneNumber, anonymous: r.signIn.anonymous },
      authorizedDomains: r.authorizedDomains, emailPrivacyConfig: r.emailPrivacyConfig,
      client: r.client && { permissions: r.client.permissions }, mfa: r.mfa && r.mfa.state,
      quota: r.quota, smsRegionConfig: r.smsRegionConfig, recaptchaConfig: r.recaptchaConfig,
      passwordPolicyConfig: r.passwordPolicyConfig && r.passwordPolicyConfig.passwordPolicyEnforcementState,
    });
  });
  await dene("Varsayılan sağlayıcılar (IdP)", async () =>
    JSON.stringify(((await c("https://identitytoolkit.googleapis.com").get(`/admin/v2/projects/${P}/defaultSupportedIdpConfigs`)).body.defaultSupportedIdpConfigs || []).map((x) => [x.name.split("/").pop(), x.enabled])));
  await dene("API anahtarları", async () =>
    JSON.stringify(((await c("https://apikeys.googleapis.com").get(`/v2/projects/${N}/locations/global/keys`)).body.keys || [])
      .map((k) => ({ ad: k.displayName, id: k.uid, kisit: k.restrictions ? Object.keys(k.restrictions) : "YOK" }))));
  await dene("IAM üyeleri", async () =>
    JSON.stringify(((await c("https://cloudresourcemanager.googleapis.com").post(`/v1/projects/${P}:getIamPolicy`, {})).body.bindings || [])
      .map((b) => [b.role, b.members])));
  await dene("Faturalandırma", async () => JSON.stringify((await c("https://cloudbilling.googleapis.com").get(`/v1/projects/${P}/billingInfo`)).body));
  await dene("Realtime Database örnekleri", async () =>
    JSON.stringify(((await c("https://firebasedatabase.googleapis.com").get(`/v1beta/projects/${N}/locations/-/instances`)).body.instances || []).map((i) => [i.name, i.state])));
  await dene("Storage kovaları", async () =>
    JSON.stringify(((await c("https://storage.googleapis.com").get(`/storage/v1/b`, { queryParams: { project: P } })).body.items || []).map((b) => [b.name, b.location, b.iamConfiguration && b.iamConfiguration.publicAccessPrevention])));
  await dene("Firestore veritabanları", async () =>
    JSON.stringify(((await c("https://firestore.googleapis.com").get(`/v1/projects/${P}/databases`)).body.databases || [])
      .map((d) => ({ ad: d.name.split("/").pop(), yer: d.locationId, silmeKorumasi: d.deleteProtectionState, pitr: d.pointInTimeRecoveryEnablement }))));
  await dene("App Check yapılandırması", async () =>
    JSON.stringify((await c("https://firebaseappcheck.googleapis.com").get(`/v1/projects/${N}/services`)).body));
  await dene("Kayıtlı uygulamalar", async () =>
    JSON.stringify(((await c("https://firebase.googleapis.com").get(`/v1beta1/projects/${P}:searchApps`)).body.apps || []).map((a) => [a.platform, a.displayName, a.appId])));
})().catch((e) => { console.error("HATA:", e.message); process.exit(1); });
