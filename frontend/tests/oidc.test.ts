import assert from "node:assert/strict";
import test from "node:test";
import {
  decodeStateCookie,
  encodeStateCookie,
  newAuthorizationState,
  oidcConfig,
  roleFromClaims,
} from "../src/lib/oidc.ts";

function withEnv(values: Record<string, string | undefined>, fn: () => void) {
  const previous: Record<string, string | undefined> = {};
  for (const [key, value] of Object.entries(values)) {
    previous[key] = process.env[key];
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  try { fn(); } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test("OIDC is optional by default", () => {
  withEnv({ ZKB_OIDC_ISSUER: undefined }, () => assert.equal(oidcConfig(), null));
});

test("OIDC configuration fails closed when incomplete", () => {
  withEnv({
    ZKB_OIDC_ISSUER: "https://id.example.test",
    ZKB_OIDC_CLIENT_ID: "zkb",
    ZKB_OIDC_CLIENT_SECRET: undefined,
    ZKB_OIDC_REDIRECT_URI: "https://kb.example.test/api/auth/oidc/callback",
  }, () => assert.throws(() => oidcConfig(), /OIDC requires/));
});

test("OIDC rejects insecure non-loopback issuer", () => {
  withEnv({ ZKB_OIDC_ISSUER: "http://id.example.test" }, () => assert.throws(() => oidcConfig(), /HTTPS/));
});

test("state cookie round trips PKCE material", () => {
  const generated = newAuthorizationState();
  const decoded = decodeStateCookie(encodeStateCookie(generated.state, generated.verifier));
  assert.deepEqual(decoded, { state: generated.state, verifier: generated.verifier });
  assert.equal(decodeStateCookie("broken"), null);
});

test("OIDC role mapping prefers admin and otherwise viewer", () => {
  const config = {
    issuer: "https://id.example.test",
    clientId: "zkb",
    clientSecret: "secret",
    redirectUri: "https://kb.example.test/api/auth/oidc/callback",
    roleClaim: "groups",
    adminValue: "zknowbase-admin",
    viewerValue: "zknowbase-viewer",
  };
  assert.equal(roleFromClaims({ groups: ["zknowbase-viewer"] }, config), "viewer");
  assert.equal(roleFromClaims({ groups: ["zknowbase-viewer", "zknowbase-admin"] }, config), "admin");
  assert.equal(roleFromClaims({ groups: ["other"] }, config), null);
});
