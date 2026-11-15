const COLORS: Record<string, string> = {
  created: "bg-slate-600/40 text-slate-300", uploaded: "bg-sky-500/20 text-sky-300", analyzing: "bg-amber-500/20 text-amber-300",
  analyzed: "bg-cyan-500/20 text-cyan-300", planned: "bg-violet-500/20 text-violet-300", rendered: "bg-lime-500/20 text-lime-300", error: "bg-rose-500/20 text-rose-300",
  completed: "bg-lime-500/20 text-lime-300", running: "bg-amber-500/20 text-amber-300", failed: "bg-rose-500/20 text-rose-300", queued: "bg-slate-600/40 text-slate-300",
  valid: "bg-lime-500/20 text-lime-300", invalid: "bg-rose-500/20 text-rose-300", infeasible: "bg-rose-500/20 text-rose-300",
};
export default function StatusChip({ status }: { status: string }) {
  return <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide ${COLORS[status] ?? "bg-ink-600 text-slate-300"}`}>{status}</span>;
}
