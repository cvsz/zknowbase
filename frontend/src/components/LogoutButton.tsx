"use client";

export function LogoutButton() {
  async function logout() {
    const response = await fetch("/api/auth/logout", { method: "POST" });
    if (response.ok) window.location.reload();
  }
  return <button onClick={()=>void logout()} className="mt-auto rounded border border-slate-700 px-3 py-2 text-left text-sm text-slate-400 hover:bg-slate-800 hover:text-white">Sign out</button>;
}
