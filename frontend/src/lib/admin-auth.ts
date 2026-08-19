import { createHmac, scryptSync, timingSafeEqual } from "node:crypto";

export const ADMIN_SESSION_COOKIE = "zkb_admin_session";
export type AdminRole = "viewer" | "admin";
export type AdminAuthSource = "local" | "oidc";

export type AdminSession = {
  v: 1;
  sub: string;
  role: AdminRole;
  auth?: AdminAuthSource;
  iat: number;
  exp: number;
};

type LocalUser = {
  username: string;
  role: AdminRole;
  password_hash: string;
};

const USERNAME_RE = /^[A-Za-z0-9._@:-]{1,120}$/;
const SESSION_TTL_SECONDS = 8 * 60 * 60;

function b64url(input: Buffer | string): string {
  return Buffer.from(input).toString("base64url");
}

function sessionSecret(): string {
  const value = process.env.ZKB_ADMIN_SESSION_SECRET ?? "";
  if (value.length < 32) throw new Error("ZKB_ADMIN_SESSION_SECRET must contain at least 32 characters");
  return value;
}

export function parseLocalUsers(raw = process.env.ZKB_ADMIN_USERS_JSON ?? ""): LocalUser[] {
  if (!raw) return [];
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("ZKB_ADMIN_USERS_JSON must be valid JSON");
  }
  if (!Array.isArray(value) || value.length < 1 || value.length > 100) throw new Error("ZKB_ADMIN_USERS_JSON must contain 1-100 users");
  const seen = new Set<string>();
  return value.map((item) => {
    if (!item || typeof item !== "object") throw new Error("Invalid local admin user entry");
    const record = item as Record<string, unknown>;
    const username = String(record.username ?? "");
    const role = record.role;
    const passwordHash = String(record.password_hash ?? "");
    if (!USERNAME_RE.test(username)) throw new Error("Invalid local admin username");
    if (role !== "viewer" && role !== "admin") throw new Error("Invalid local admin role");
    const key = username.toLowerCase();
    if (seen.has(key)) throw new Error("Duplicate local admin username");
    seen.add(key);
    validateScryptHash(passwordHash);
    return { username, role, password_hash: passwordHash };
  });
}

function validateScryptHash(encoded: string): void {
  const parts = encoded.split("$");
  if (parts.length !== 7 || parts[0] !== "scrypt" || parts[1] !== "v1") throw new Error("Admin password hash must use scrypt$v1 format");
  const n = Number(parts[2]);
  const r = Number(parts[3]);
  const p = Number(parts[4]);
  if (!Number.isInteger(n) || n < 16_384 || n > 262_144 || (n & (n - 1)) !== 0) throw new Error("Invalid scrypt N parameter");
  if (!Number.isInteger(r) || r < 1 || r > 32 || !Number.isInteger(p) || p < 1 || p > 16) throw new Error("Invalid scrypt r/p parameter");
  const salt = Buffer.from(parts[5], "base64url");
  const digest = Buffer.from(parts[6], "base64url");
  if (salt.length < 16 || digest.length !== 64) throw new Error("Invalid scrypt salt/digest length");
}

export function verifyScryptPassword(password: string, encoded: string): boolean {
  validateScryptHash(encoded);
  const [, , nRaw, rRaw, pRaw, saltRaw, digestRaw] = encoded.split("$");
  const n = Number(nRaw); const r = Number(rRaw); const p = Number(pRaw);
  const salt = Buffer.from(saltRaw, "base64url");
  const expected = Buffer.from(digestRaw, "base64url");
  const maxmem = Math.max(64 * 1024 * 1024, 256 * n * r);
  const actual = scryptSync(password, salt, expected.length, { N: n, r, p, maxmem });
  return timingSafeEqual(actual, expected);
}

export function authenticateLocalUser(username: string, password: string): { username: string; role: AdminRole } | null {
  if (!USERNAME_RE.test(username) || password.length < 1 || password.length > 4096) return null;
  const users = parseLocalUsers();
  if (users.length === 0) return null;
  const user = users.find((candidate) => candidate.username.toLowerCase() === username.toLowerCase());
  const comparisonHash = user?.password_hash ?? users[0].password_hash;
  const valid = verifyScryptPassword(password, comparisonHash);
  if (!user || !valid) return null;
  return { username: user.username, role: user.role };
}

export function createAdminSession(username: string, role: AdminRole, nowSeconds = Math.floor(Date.now() / 1000), auth: AdminAuthSource = "local"): string {
  if (!USERNAME_RE.test(username)) throw new Error("Invalid admin session subject");
  const payload: AdminSession = { v: 1, sub: username, role, auth, iat: nowSeconds, exp: nowSeconds + SESSION_TTL_SECONDS };
  const body = b64url(JSON.stringify(payload));
  const signature = createHmac("sha256", sessionSecret()).update(body).digest("base64url");
  return `${body}.${signature}`;
}

export function verifyAdminSession(token: string | undefined, nowSeconds = Math.floor(Date.now() / 1000)): AdminSession | null {
  if (!token || token.length > 8192) return null;
  const [body, signature, extra] = token.split(".");
  if (!body || !signature || extra) return null;
  const expected = createHmac("sha256", sessionSecret()).update(body).digest();
  const supplied = Buffer.from(signature, "base64url");
  if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) return null;
  let payload: unknown;
  try { payload = JSON.parse(Buffer.from(body, "base64url").toString("utf8")); } catch { return null; }
  if (!payload || typeof payload !== "object") return null;
  const value = payload as Record<string, unknown>;
  const auth = value.auth === undefined ? "local" : value.auth;
  if (value.v !== 1 || typeof value.sub !== "string" || !USERNAME_RE.test(value.sub) || (value.role !== "viewer" && value.role !== "admin") || (auth !== "local" && auth !== "oidc") || typeof value.iat !== "number" || typeof value.exp !== "number" || value.iat > nowSeconds + 60 || value.exp <= nowSeconds || value.exp - value.iat > SESSION_TTL_SECONDS) return null;
  const subject = value.sub as string;
  const role = value.role as AdminRole;
  if (auth === "local") {
    const configured = parseLocalUsers().find((user) => user.username.toLowerCase() === subject.toLowerCase());
    if (!configured || configured.role !== role) return null;
  } else if (!(process.env.ZKB_OIDC_ISSUER ?? "").trim()) {
    return null;
  }
  return { v: 1, sub: subject, role, auth: auth as AdminAuthSource, iat: value.iat as number, exp: value.exp as number };
}

export function cookieSecure(): boolean {
  return (process.env.ZKB_ADMIN_COOKIE_SECURE ?? "false").toLowerCase() === "true";
}

export function canProxy(session: AdminSession, method: string, path: string[]): boolean {
  if (session.role === "admin") return true;
  const route = path.join("/");
  if (method === "GET") return route === "health" || route === "documents" || route === "ingest/jobs" || route.startsWith("ingest/jobs/");
  if (method === "POST") return route === "query" || route === "search";
  return false;
}

export function sameOrigin(headers: Headers): boolean {
  const origin = headers.get("origin");
  const host = headers.get("x-forwarded-host") ?? headers.get("host");
  if (!origin || !host) return false;
  try { return new URL(origin).host === host; } catch { return false; }
}
