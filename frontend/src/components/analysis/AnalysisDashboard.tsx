import { useMemo, useState } from "react";
import { CheckCircle2, ChevronRight, Info, XCircle } from "lucide-react";
import { useProject } from "../../context/ProjectContext";
import { ProofNode } from "../../services/api";
import { fmt, scoreColor } from "../../utils/format";

type Tab = "overview" | "astar" | "csp" | "expert" | "agent";
const TABS: [Tab, string][] = [["overview", "Overview"], ["astar", "A* search"], ["csp", "CSP validation"], ["expert", "Expert system"], ["agent", "Agent log"]];

export default function AnalysisDashboard() {
  const { analysis, plan } = useProject();
  const [tab, setTab] = useState<Tab>("overview");
  if (!analysis) return <div className="p-8 text-slate-500 text-sm">Analysis is not available yet.</div>;
  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="flex gap-1 px-3 py-2 text-xs">{TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={`px-3 py-1 rounded-full font-medium ${tab === k ? "bg-accent text-white" : "bg-ink-700 text-slate-300"}`}>{l}</button>)}</div>
      <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-3">
        {tab === "overview" && <Overview />}
        {tab !== "overview" && !plan && <div className="panel p-6 text-sm text-slate-400">Create an editing plan with the AI assistant to see how the {TABS.find((t) => t[0] === tab)![1]} stage ran on your video.</div>}
        {plan && tab === "astar" && <AStarView />}{plan && tab === "csp" && <CspView />}{plan && tab === "expert" && <ExpertView />}
        {tab === "agent" && <AgentView />}
      </div>
    </div>);
}

const Stat = ({ k, v, sub }: { k: string; v: string | number; sub?: string }) => (<div className="panel p-3"><div className="label">{k}</div><div className="text-xl font-bold mt-0.5">{v}</div>{sub && <div className="text-[11px] text-slate-500">{sub}</div>}</div>);
const Explain = ({ children }: { children: React.ReactNode }) => <div className="flex gap-2 text-xs text-slate-400 bg-accent/5 border border-accent/20 rounded-lg p-2.5"><Info size={14} className="text-accent-soft shrink-0 mt-0.5" /><div>{children}</div></div>;

function Overview() {
  const { analysis: a, plan } = useProject();
  const [sel, setSel] = useState<number | null>(null);
  if (!a) return null;
  const s = a.summary, selected = new Set(plan?.clips.map((c) => c.scene_id));
  const maxW = 560, barH = 150, bw = Math.max(10, Math.min(46, (maxW - 20) / a.scenes.length - 4));
  const scene = a.scenes.find((x) => x.scene_id === sel) ?? a.scenes[0];
  return (<>
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
      <Stat k="Duration" v={fmt(s.duration)} /><Stat k="Scenes" v={s.scene_count} sub={`${s.important_scenes} scoring ≥ 60`} />
      <Stat k="Audio activity" v={s.speech_duration != null ? `${s.speech_duration.toFixed(1)}s` : "—"} sub="energy + transcript" /><Stat k="Silence" v={s.silence_duration != null ? `${s.silence_duration.toFixed(1)}s` : "—"} />
      <Stat k="Transcript" v={s.transcript_status === "ok" ? `${a.transcript.segments.length} seg` : "none"} sub={s.transcript_source} /></div>
    {s.transcript_status !== "ok" && <Explain><b>No transcript.</b> {s.transcript_message} Speech-relevance, topic relevance and subtitles are reported as <i>missing</i> (excluded from scoring and renormalised) — never assumed.</Explain>}
    <div className="panel p-3">
      <div className="label mb-2">Scene importance (click a bar) — green outline = selected in current plan</div>
      <svg viewBox={`0 0 ${maxW} ${barH + 28}`} className="w-full max-w-[640px]">
        {[0, 50, 100].map((g) => <g key={g}><line x1="26" x2={maxW} y1={barH - g * barH / 100 + 4} y2={barH - g * barH / 100 + 4} stroke="#262c3f" /><text x="0" y={barH - g * barH / 100 + 8} fontSize="9" fill="#64748b">{g}</text></g>)}
        {a.scenes.map((sc, i) => { const h = sc.importance * barH / 100, x = 32 + i * (bw + 4); return (
          <g key={sc.scene_id} onClick={() => setSel(sc.scene_id)} className="cursor-pointer">
            <rect x={x} y={barH - h + 4} width={bw} height={Math.max(1, h)} rx="3" fill={scoreColor(sc.importance)} opacity={sel === sc.scene_id ? 1 : 0.75} stroke={selected.has(sc.scene_id) ? "#fff" : "none"} strokeWidth="2" />
            <text x={x + bw / 2} y={barH + 18} fontSize="9" fill="#94a3b8" textAnchor="middle">#{sc.scene_id}</text></g>); })}
      </svg></div>
    <div className="panel p-3 space-y-2">
      <div className="flex items-center justify-between"><div className="font-semibold text-sm">Scene #{scene.scene_id} · {fmt(scene.start, true)}–{fmt(scene.end, true)} · score {scene.importance.toFixed(1)}</div><span className="chip">{scene.boundary_method}</span></div>
      <div className="text-xs text-slate-300">{scene.score_detail.explanation}</div>
      <div className="grid grid-cols-5 gap-1.5 text-[10px]">{Object.entries(scene.score_detail.contributions).map(([k, v]) => (<div key={k} className="bg-ink-900 rounded p-1.5"><div className="text-slate-500 truncate">{k.replace("_", " ")}</div><div className="font-bold text-sm">{v.toFixed(1)}</div></div>))}</div>
      {scene.score_detail.missing.length > 0 && <div className="text-[11px] text-amber-300">Missing features (excluded, not scored as 0): {scene.score_detail.missing.join(", ")}</div>}
      <div className="text-[11px] text-slate-500">speech density {scene.speech_density != null ? (scene.speech_density * 100).toFixed(0) + "%" : "—"} · silence {scene.silence_pct ?? "—"}% · motion {scene.motion?.toFixed(4) ?? "—"} · loudness {scene.loudness_db ?? "—"} dB</div>
      {scene.transcript && <div className="text-xs italic text-slate-400">“{scene.transcript}”</div>}
    </div>
    <Explain>Importance = weighted sum of normalised features (speech relevance 30%, speech activity 20%, visual activity 15%, distinctiveness 15%, topic relevance 20%). Weights are configurable defaults, not scientific constants. Scene detection: {a.scene_notes.join("; ")}.</Explain>
  </>);
}

function AStarView() {
  const { plan } = useProject(); const a = plan!.algorithms.astar;
  if (!a?.candidate_ids) return <div className="panel p-4 text-sm">No search ran.</div>;
  const Seq = ({ ids, label, cost }: { ids: number[]; label: string; cost: number }) => (<div><div className="label mb-1">{label} · cost {cost}</div><div className="flex flex-wrap items-center gap-1">{ids.map((id, i) => <span key={i} className="flex items-center"><span className="chip !bg-accent/20 !text-violet-200">#{id}</span>{i < ids.length - 1 && <ChevronRight size={12} className="text-slate-600" />}</span>)}</div></div>);
  return (<>
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-2"><Stat k="Algorithm" v={a.algorithm === "astar" ? "A*" : a.algorithm === "beam" ? "Beam" : a.algorithm} sub={a.optimal ? "optimal (admissible h)" : "NOT guaranteed optimal"} /><Stat k="Expanded" v={a.expanded} /><Stat k="Generated" v={a.generated} /><Stat k="States explored" v={a.explored_states} /><Stat k="Search time" v={`${(a.seconds * 1000).toFixed(2)} ms`} /></div>
    <div className="panel p-3 space-y-3"><Seq ids={a.order_scene_ids} label="A* order" cost={a.cost} /><Seq ids={a.chronological_scene_ids} label="Chronological order" cost={a.chronological_cost} />
      <div className="text-sm">Applied: <b>{a.applied}</b> · A* vs chronological: <b className={a.improvement_vs_chronological > 0 ? "text-lime-400" : "text-slate-300"}>{a.improvement_vs_chronological > 0 ? `${a.improvement_pct}% cheaper` : "no improvement (chronological already optimal under this cost model)"}</b></div>
      <div className="text-[11px] text-slate-500">{a.note}{a.cost_notes?.length ? " · " + a.cost_notes.join("; ") : ""}</div></div>
    <div className="panel p-3 overflow-x-auto"><div className="label mb-2">Search visualisation: first expansions (f = g + h)</div>
      <table className="w-full text-[11px] font-mono"><thead className="text-slate-500 text-left"><tr><th>#</th><th>path</th><th>g</th><th>h</th><th>f</th></tr></thead>
        <tbody>{a.trace.slice(0, 14).map((t) => <tr key={t.step} className="border-t border-ink-700"><td>{t.step}</td><td>{t.path.map((p) => "#" + p).join("→")}</td><td>{t.g}</td><td>{t.h}</td><td className="text-accent-soft">{t.f}</td></tr>)}</tbody></table></div>
    <Explain>A* keeps an OPEN priority queue ordered by f = g + h. g is the accumulated transition cost (visual discontinuity, loudness jump, semantic inconsistency, temporal jump). h is a minimum-spanning-tree lower bound over the unvisited scenes — a path through all scenes is a spanning tree, so h never overestimates (admissible). Beyond 9 candidates a beam search is used and flagged as non-optimal.</Explain>
  </>);
}

function CspView() {
  const { plan } = useProject(); const c = plan!.algorithms.csp;
  const failed = new Set(plan!.validation.violations.map((v) => v.constraint));
  return (<>
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-2"><Stat k="Status" v={c.status} /><Stat k="Nodes" v={c.nodes} /><Stat k="Backtracks" v={c.backtracks} sub={`${c.pruned_values} values pruned by forward checking`} /><Stat k="Independent validation" v={plan!.validation.status} sub={`${plan!.validation.checked ?? "—"} checks`} /></div>
    <div className="panel p-3"><div className="label mb-2">Constraints</div>{c.constraints.map((k) => (<div key={k.name} className="flex items-center gap-2 text-xs py-1 border-b border-ink-700 last:border-0">
      {c.status === "satisfied" && !failed.has(k.name) ? <CheckCircle2 size={13} className="text-lime-400" /> : <XCircle size={13} className="text-rose-400" />}<span className="font-mono text-slate-200">{k.name}</span><span className="text-slate-500">{k.description}</span></div>))}</div>
    {c.assignment && <div className="panel p-3"><div className="label mb-2">Solution (variable = value)</div><div className="grid grid-cols-2 lg:grid-cols-3 gap-1.5 text-[11px] font-mono">{Object.entries(c.assignment).map(([k, v]) => <div key={k} className="bg-ink-900 rounded px-2 py-1 flex justify-between"><span className="text-slate-500">{k}</span><span>{String(v)}</span></div>)}</div></div>}
    {Object.keys(c.failed_constraints ?? {}).length > 0 && <div className="panel p-3 text-xs"><div className="label mb-1">Constraints that rejected values during search</div>{Object.entries(c.failed_constraints).map(([k, v]) => <div key={k}>{k}: {v}×</div>)}</div>}
    {plan!.validation.suggestions?.length ? <div className="panel p-3 text-xs text-amber-300 space-y-1"><div className="label">Suggested alternatives</div>{plan!.validation.suggestions.map((s, i) => <div key={i}>→ {s}</div>)}</div> : null}
    <Explain>Backtracking search assigns one variable at a time: MRV picks the variable with the fewest legal values (ties → highest importance), values are tried closest-to-utility-share first, and forward checking prunes values that already break a constraint. The same rules are re-checked by an independent validator before any render.</Explain>
  </>);
}

const Proof = ({ n, d = 0 }: { n: ProofNode; d?: number }) => (<div style={{ marginLeft: d * 14 }} className="text-[11px] py-0.5"><span className={n.proved ? "text-lime-400" : "text-rose-400"}>{n.proved ? "✓" : "✗"}</span> <span className="font-mono">{n.goal}</span> <span className="text-slate-500">via {n.via}</span>{n.children.map((c, i) => <Proof key={i} n={c} d={d + 1} />)}</div>);

function ExpertView() {
  const { plan } = useProject(); const e = plan!.algorithms.expert;
  const [only, setOnly] = useState(true);
  const rows = useMemo(() => e.rules.filter((r) => !only || r.fired), [e, only]);
  return (<>
    <div className="panel p-3"><div className="flex items-center justify-between mb-2"><div className="label">Rule executions (forward chaining)</div><label className="text-xs flex items-center gap-1.5 text-slate-400"><input type="checkbox" checked={only} onChange={(x) => setOnly(x.target.checked)} /> fired only</label></div>
      <div className="space-y-1.5">{rows.map((r, i) => (<div key={i} className="bg-ink-900 rounded-lg p-2 text-[11px]">
        <div className="flex items-center gap-2"><span className={`font-bold ${r.fired ? "text-lime-400" : "text-slate-500"}`}>{r.rule_id}</span><span className="font-medium">{r.name}</span><span className="chip">{r.scope}{r.target !== "project" ? ` · ${r.target}` : ""}</span><span className="ml-auto">{r.fired ? "FIRED" : "not fired"}</span></div>
        <div className="font-mono text-slate-500 mt-1 break-words">{r.condition}</div>
        <div className="text-slate-500">facts: {JSON.stringify(r.facts_evaluated)}</div>
        <div className="text-slate-300 mt-0.5">{r.fired ? `→ ${r.recommendation} ` : ""}{r.explanation}</div></div>))}</div></div>
    {e.backward && <div className="panel p-3"><div className="label mb-2">Backward chaining — goal: vertical_reel_ready</div><Proof n={e.backward} />
      {e.backward.unmet_requirements?.length ? <div className="text-xs text-rose-300 mt-2">Unmet: {e.backward.unmet_requirements.join("; ")}</div> : null}</div>}
    <Explain>Forward chaining starts from facts (aspect ratio, transcript availability, scene measurements) and fires every rule whose IF-part holds, repeating until no new fact is derived (e.g. R4 derives <i>reframe_scheduled</i>, which then enables R8 and R9). Backward chaining starts from a goal and recursively proves the premises of rules that conclude it.</Explain>
  </>);
}

function AgentView() {
  const { decisions } = useProject();
  const order = ["perceive", "understand", "plan", "decide", "validate", "act", "evaluate"];
  const sorted = [...decisions].sort((a, b) => a.decision_id - b.decision_id);
  return (<>
    <div className="flex gap-1 flex-wrap">{order.map((p) => <span key={p} className="chip">{p} · {decisions.filter((d) => d.phase === p).length}</span>)}</div>
    <div className="panel p-3 space-y-2">{sorted.length === 0 && <div className="text-sm text-slate-500">No decisions logged yet.</div>}
      {sorted.map((d) => (<div key={d.decision_id} className="border-l-2 border-accent/50 pl-3 text-xs"><div className="flex gap-2 items-center"><span className="chip !bg-accent/20 !text-violet-200">{d.phase}</span><b>{d.agent_name}</b><span className="text-slate-600 ml-auto">{new Date(d.timestamp).toLocaleTimeString()}</span></div>
        <div className="mt-0.5">{d.decision}</div>{d.explanation && <div className="text-slate-500 mt-0.5">{d.explanation}</div>}</div>))}</div>
    <Explain><b>PEAS.</b> Performance: content preserved, duration accuracy, continuity, constraint satisfaction. Environment: video, audio, metadata, instruction. Actuators: trim, select, sequence, subtitle, audio-process, render. Sensors: frames, audio signal, transcript, scene detector. The agent is goal-based (hit the requested format/duration) and utility-based (maximise scene importance minus transition cost).</Explain>
  </>);
}
