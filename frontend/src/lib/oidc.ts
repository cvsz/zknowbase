import { createHash, randomBytes } from "node:crypto";
import type { AdminRole } from "@/lib/admin-auth";

export const OIDC_STATE_COOKIE = "zkb_oidc_state";
const MAX_DISCOVERY_BYTES = 64 * 1024;

export type OidcConfig = {
  issuer: string;
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  roleClaim: string;
  adminValue: string;
  viewerValue: string;
};

type Discovery = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  userinfo_endpoint: string;
};

function safeUrl(raw: string): URL {
  const url = new URL(raw);
  const local = url.hostname === "localhost" || url.hostname === "127.0.0.1" || url.hostname === "::1";
  if (url.protocol !== "https:" && !(local && url.protocol === "http:")) {
    throw new Error("OIDC endpoints must use HTTPS except loopback development issuers");
  }
  if (url.username || url.password || url.hash) throw new Error("Invalid OIDC URL");
  return url;
}

export function oidcConfig(): OidcConfig | null {
  const issuerRaw = (process.env.ZKB_OIDC_ISSUER ?? "").trim();
  if (!issuerRaw) return null;
  const issuer = safeUrl(issuerRaw).toString().replace(/\/$/, "");
  const clientId = (process.env.ZKB_OIDC_CLIENT_ID ?? "").trim();
  const clientSecret = process.env.ZKB_OIDC_CLIENT_SECRET ?? "";
  const redirectUri = (process.env.ZKB_OIDC_REDIRECT_URI ?? "").trim();
  if (!clientId || !clientSecret || !redirectUri) {
    throw new Error("OIDC requires ZKB_OIDC_CLIENT_ID, ZKB_OIDC_CLIENT_SECRET, and ZKB_OIDC_REDIRECT_URI");
  }
  safeUrl(redirectUri);
  return {
    issuer,
    clientId,
    clientSecret,
    redirectUri,
    roleClaim: (process.env.ZKB_OIDC_ROLE_CLAIM ?? "groups").trim() || "groups",
    adminValue: (process.env.ZKB_OIDC_ADMIN_VALUE ?? "zknowbase-admin").trim(),
    viewerValue: (process.env.ZKB_OIDC_VIEWER_VALUE ?? "zknowbase-viewer").trim(),
  };
}

function sameIssuerOrigin(issuer: string, endpoint: string): string {
  const issuerUrl = safeUrl(issuer);
  const endpointUrl = safeUrl(endpoint);
  if (endpointUrl.origin !== issuerUrl.origin) throw new Error("OIDC discovery endpoint origin must match issuer origin");
  return endpointUrl.toString();
}

async function boundedJson(response: Response): Promise<Record<string, unknown>> {
  if (!response.ok) throw new Error(`OIDC upstream returned ${response.status}`);
  const length = Number(response.headers.get("content-length") ?? "0");
  if (length > MAX_DISCOVERY_BYTES) throw new Error("OIDC response too large");
  const text = await response.text();
  if (Buffer.byteLength(text) > MAX_DISCOVERY_BYTES) throw new Error("OIDC response too large");
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid OIDC JSON response");
  return value as Record<string, unknown>;
}

export async function discover(config: OidcConfig): Promise<Discovery> {
  const discoveryUrl = `${config.issuer}/.well-known/openid-configuration`;
  const value = await boundedJson(await fetch(discoveryUrl, { cache: "no-store", redirect: "error" }));
  if (value.issuer !== config.issuer) throw new Error("OIDC discovery issuer mismatch");
  const authorization = sameIssuerOrigin(config.issuer, String(value.authorization_endpoint ?? ""));
  const token = sameIssuerOrigin(config.issuer, String(value.token_endpoint ?? ""));
  const userinfo = sameIssuerOrigin(config.issuer, String(value.userinfo_endpoint ?? ""));
  return { issuer: config.issuer, authorization_endpoint: authorization, token_endpoint: token, userinfo_endpoint: userinfo };
}

export function newAuthorizationState(): { state: string; verifier: string; challenge: string } {
  const state = randomBytes(32).toString("base64url");
  const verifier = randomBytes(48).toString("base64url");
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  return { state, verifier, challenge };
}

export function encodeStateCookie(state: string, verifier: string): string {
  return Buffer.from(JSON.stringify({ state, verifier }), "utf8").toString("base64url");
}

export function decodeStateCookie(raw: string | undefined): { state: string; verifier: string } | null {
  if (!raw || raw.length > 4096) return null;
  try {
    const value = JSON.parse(Buffer.from(raw, "base64url").toString("utf8")) as Record<string, unknown>;
    if (typeof value.state !== "string" || typeof value.verifier !== "string") return null;
    if (value.state.length < 32 || value.verifier.length < 43) return null;
    return { state: value.state, verifier: value.verifier };
  } catch {
    return null;
  }
}

export function roleFromClaims(claims: Record<string, unknown>, config: OidcConfig): AdminRole | null {
  const raw = claims[config.roleClaim];
  const values = Array.isArray(raw) ? raw.map(String) : typeof raw === "string" ? [raw] : [];
  if (config.adminValue && values.includes(config.adminValue)) return "admin";
  if (config.viewerValue && values.includes(config.viewerValue)) return "viewer";
  return null;
}

export async function exchangeAndLoadUser(code: string, verifier: string, config: OidcConfig): Promise<{ subject: string; role: AdminRole }> {
  const discovery = await discover(config);
  const tokenResponse = await fetch(discovery.token_endpoint, {
    method: "POST",
    redirect: "error",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: config.redirectUri,
      client_id: config.clientId,
      client_secret: config.clientSecret,
      code_verifier: verifier,
    }),
  });
  const token = await boundedJson(tokenResponse);
  const accessToken = typeof token.access_token === "string" ? token.access_token : "";
  if (!accessToken || accessToken.length > 16384) throw new Error("OIDC token response missing access_token");
  const claims = await boundedJson(await fetch(discovery.userinfo_endpoint, {
    cache: "no-store",
    redirect: "error",
    headers: { authorization: `Bearer ${accessToken}`, accept: "application/json" },
  }));
  const subject = typeof claims.sub === "string" ? claims.sub : "";
  if (!subject || subject.length > 120 || !/^[A-Za-z0-9._@:-]+$/.test(subject)) throw new Error("OIDC userinfo missing valid subject");
  const role = roleFromClaims(claims, config);
  if (!role) throw new Error("OIDC subject is not authorized for zknowbase");
  return { subject, role };
}
