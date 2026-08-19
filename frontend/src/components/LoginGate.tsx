"use client";

import { FormEvent, useState } from "react";
import { LockKeyhole } from "lucide-react";

export function LoginGate({ oidcEnabled = false }: { oidcEnabled?: boolean }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ detail: "Login failed" }));
        throw new Error(payload.detail ?? "Login failed");
      }
      window.location.reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return <main className="flex min-h-screen items-center justify-center bg-slate-950 p-6">
    <form onSubmit={submit} className="w-full max-w-sm space-y-5 rounded-2xl border border-slate-800 bg-slate-900 p-7 shadow-2xl">
      <div><LockKeyhole className="mb-4"/><h1 className="text-2xl font-semibold">zknowbase Admin</h1><p className="mt-2 text-sm text-slate-400">Local administrator session</p></div>
      <label className="block text-sm">Username<input autoComplete="username" required value={username} onChange={e=>setUsername(e.target.value)} className="mt-2 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2"/></label>
      <label className="block text-sm">Password<input type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)} className="mt-2 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2"/></label>
      <button disabled={busy} className="w-full rounded bg-indigo-500 px-4 py-2 font-medium disabled:opacity-50">{busy ? "Signing in…" : "Sign in"}</button>
      {oidcEnabled && <>
        <div className="flex items-center gap-3 text-xs text-slate-500"><span className="h-px flex-1 bg-slate-800"/>or<span className="h-px flex-1 bg-slate-800"/></div>
        <a href="/api/auth/oidc/login" className="block w-full rounded border border-slate-700 px-4 py-2 text-center font-medium hover:bg-slate-800">Sign in with OIDC</a>
      </>}
      {message && <p className="text-sm text-rose-300">{message}</p>}
    </form>
  </main>;
}
