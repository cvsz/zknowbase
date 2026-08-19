import Link from "next/link";
import { BrainCircuit, Database, MessageSquareText, Upload } from "lucide-react";

const items = [
  ["Dashboard", "/", BrainCircuit], ["Ingestion", "/ingest", Upload],
  ["Vectors", "/vectors", Database], ["Playground", "/playground", MessageSquareText],
] as const;

export function Nav() {
  return <aside className="w-64 border-r border-slate-800 bg-slate-900/60 p-5">
    <div className="mb-8 text-xl font-semibold">zknowbase</div>
    <nav className="space-y-2">{items.map(([label,href,Icon]) =>
      <Link key={href} href={href} className="flex items-center gap-3 rounded-lg px-3 py-2 text-slate-300 hover:bg-slate-800 hover:text-white"><Icon size={18}/>{label}</Link>
    )}</nav>
  </aside>;
}
