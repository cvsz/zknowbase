import assert from "node:assert/strict";
import { randomBytes, scryptSync } from "node:crypto";
import test from "node:test";

import {
  authenticateLocalUser,
  canProxy,
  createAdminSession,
  parseLocalUsers,
  sameOrigin,
  verifyAdminSession,
  type AdminSession,
} from "../src/lib/admin-auth.ts";

function passwordHash(password: string): string {
  const N = 32768, r = 8, p = 1;
  const salt = randomBytes(16);
  const digest = scryptSync(password, salt, 64, { N, r, p, maxmem: 128 * 1024 * 1024 });
  return `scrypt$v1$${N}$${r}$${p}$${salt.toString("base64url")}$${digest.toString("base64url")}`;
}

const password = "correct horse battery staple";
process.env.ZKB_ADMIN_SESSION_SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef";
process.env.ZKB_ADMIN_USERS_JSON = JSON.stringify([
  { username: "admin", role: "admin", password_hash: passwordHash(password) },
  { username: "reader", role: "viewer", password_hash: passwordHash(password) },
]);

test("local users authenticate from scrypt hashes", () => {
  assert.equal(parseLocalUsers().length, 2);
  assert.deepEqual(authenticateLocalUser("ADMIN", password), { username: "admin", role: "admin" });
  assert.equal(authenticateLocalUser("admin", "incorrect"), null);
  assert.equal(authenticateLocalUser("missing", password), null);
});

test("signed sessions reject tampering and expiry", () => {
  const token = createAdminSession("admin", "admin", 1_000);
  assert.equal(verifyAdminSession(token, 1_001)?.sub, "admin");
  assert.equal(verifyAdminSession(`${token}x`, 1_001), null);
  assert.equal(verifyAdminSession(token, 1_000 + 8 * 60 * 60), null);
});

test("viewer role is retrieval-only through the proxy", () => {
  const viewer: AdminSession = { v: 1, sub: "reader", role: "viewer", iat: 1, exp: 2 };
  assert.equal(canProxy(viewer, "GET", ["documents"]), true);
  assert.equal(canProxy(viewer, "GET", ["ingest", "jobs", "job-1"]), true);
  assert.equal(canProxy(viewer, "POST", ["query"]), true);
  assert.equal(canProxy(viewer, "POST", ["search"]), true);
  assert.equal(canProxy(viewer, "POST", ["ingest"]), false);
  assert.equal(canProxy(viewer, "DELETE", ["documents", "doc-1"]), false);
  assert.equal(canProxy(viewer, "GET", ["service-keys"]), false);
  assert.equal(canProxy(viewer, "GET", ["audit"]), false);

  const admin: AdminSession = { ...viewer, sub: "admin", role: "admin" };
  assert.equal(canProxy(admin, "DELETE", ["documents", "doc-1"]), true);
});

test("state-changing browser calls require matching origin and host", () => {
  const good = new Headers({ origin: "http://localhost:3000", host: "localhost:3000" });
  const bad = new Headers({ origin: "https://evil.example", host: "localhost:3000" });
  assert.equal(sameOrigin(good), true);
  assert.equal(sameOrigin(bad), false);
});
