#!/usr/bin/env node
import { randomBytes, scryptSync } from "node:crypto";

const username = process.argv[2] || "admin";
const role = process.argv[3] || "admin";
if (!/^[A-Za-z0-9._@-]{1,120}$/.test(username)) throw new Error("Invalid username");
if (!new Set(["viewer", "admin"]).has(role)) throw new Error("Role must be viewer or admin");

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const password = Buffer.concat(chunks).toString("utf8").replace(/[\r\n]+$/, "");
if (password.length < 12) throw new Error("Use a password of at least 12 characters");

const N = 32768, r = 8, p = 1;
const salt = randomBytes(16);
const digest = scryptSync(password, salt, 64, { N, r, p, maxmem: 128 * 1024 * 1024 });
const password_hash = `scrypt$v1$${N}$${r}$${p}$${salt.toString("base64url")}$${digest.toString("base64url")}`;
const users = JSON.stringify([{ username, role, password_hash }]);
// Compose treats single-quoted .env values literally, preserving the `$` separators
// inside scrypt hashes rather than interpreting them as variable interpolation.
console.log(`ZKB_ADMIN_USERS_JSON='${users}'`);
