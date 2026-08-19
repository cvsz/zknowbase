import Link from "next/link";
import { BrainCircuit, Database, MessageSquareText, Upload } from "lucide-react";
import type { AdminRole } from "@/lib/admin-auth";
import { LogoutButton } from "@/components/LogoutButton";

const items = [
  ["Dashboard", "/", BrainCircuit, "viewer"],
  ["Ingestion", "/ingest", Upload, "admin"],
  ["Vectors", "/vectors", Database, "viewer"],
  ["Playground", "/playground", MessageSquareText, "viewer"],
] as const;

export function Nav({ username, role }: { username: string; role: AdminRole }) {
  return <aside className="flex w-64 flex-col border-r border-slate-800 bg-slate-900/60 p-5">
    <div className="mb-8"><div className="text-xl font-semibold">zknowbase</div><div className="mt-2 text-xs text-slate-500">{username} · {role}</div></div>
    <nav className="space-y-2">{items.filter(([, , , minimum]) => role === "admin" || minimum === "viewer").map(([label,href,Icon]) =>
      <Link key={href} href={href} className="flex items-center gap-3 rounded-lg px-3 py-2 text-slate-300 hover:bg-slate-800 hover:text-white"><Icon size={18}/>{label}</Link>
    )}</nav>
    <LogoutButton/>
  </aside>;
}
