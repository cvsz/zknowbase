"use client";
import { useEffect, useState } from "react";
import { RefreshCw, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { DocumentRecord } from "@/lib/types";

export default function Vectors(){
 const [docs,setDocs]=useState<DocumentRecord[]>([]),[busy,setBusy]=useState("");
 const load=()=>api.documents().then(setDocs); useEffect(()=>{void load()},[]);
 async function remove(id:string){setBusy(id);try{await api.remove(id);await load()}finally{setBusy("")}}
 async function reindex(id:string){setBusy(id);try{await api.reindex(id);await load()}finally{setBusy("")}}
 return <section className="space-y-6"><div><h1 className="text-3xl font-semibold">Vector management</h1><p className="mt-2 text-slate-400">Inspect corpus state, re-index sources, or remove vectors.</p></div>
 <div className="overflow-hidden rounded-xl border border-slate-800"><table className="w-full text-sm"><thead className="bg-slate-900 text-left text-slate-400"><tr><th className="p-4">Document</th><th>Source</th><th>Status</th><th>Chunks</th><th className="pr-4 text-right">Actions</th></tr></thead><tbody className="divide-y divide-slate-800">{docs.map(d=><tr key={d.id}><td className="p-4"><div className="max-w-md truncate">{d.name}</div><div className="text-xs text-slate-500">{d.id}</div></td><td>{d.source_type}</td><td>{d.status}</td><td>{d.chunk_count}</td><td className="pr-4"><div className="flex justify-end gap-2"><button disabled={busy===d.id} onClick={()=>void reindex(d.id)} className="rounded border border-slate-700 p-2"><RefreshCw size={15}/></button><button disabled={busy===d.id} onClick={()=>void remove(d.id)} className="rounded border border-red-900 p-2 text-red-300"><Trash2 size={15}/></button></div></td></tr>)}</tbody></table></div></section>
}
