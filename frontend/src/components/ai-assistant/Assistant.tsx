import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, ChevronDown, Loader2, Send, Sliders, User, XCircle } from "lucide-react";
import { useProject } from "../../context/ProjectContext";
import { Plan, thumbUrl } from "../../services/api";
import { fmt, scoreColor } from "../../utils/format";
import StatusChip from "../editor/StatusChip";

interface Msg { role: "user" | "ai"; text?: string; plan?: Plan }
const SUGGESTIONS = [
  "Create a 30-second vertical Instagram Reel. Preserve important speech, remove unnecessary silence, add animated subtitles and use smooth transitions.",
  "Make this video suitable for YouTube Shorts",
  "Create a cinematic 20-second landscape edit with fade transitions",
  "Remove pauses but preserve every important sentence, keep the original order",
];

export default function Assistant({ onApply }: { onApply: () => void }) {
  const { project, analysis, plan, makePlan, busy, startRender } = useProject();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [showCfg, setShowCfg] = useState(false);
  const [ov, setOv] = useState<Record<string, any>>({});
  const end = useRef<HTMLDivElement>(null);
  const greeted = useRef(false);

  useEffect(() => {
    if (analysis && !greeted.current) {
      greeted.current = true;
      const s = analysis.summary;
      setMsgs((m) => [...m, { role: "ai", text: `I analyzed your video: ${s.scene_count} scene${s.scene_count === 1 ? "" : "s"}, ${s.speech_duration != null ? `${s.speech_duration.toFixed(0)} s of audio activity` : "no audio"}, ${s.silence_duration != null ? `${s.silence_duration.toFixed(0)} s of silence` : ""}. ` +
        (s.transcript_status === "ok" ? `Transcript: ${s.transcript_source}.` : "No transcript is available (Whisper model not loaded) — subtitles and speech-based scoring need one; you can import an SRT from the Media panel.") + " Tell me how to edit it." }]);
    }
  }, [analysis]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  const send = async (t = text) => {
    if (!t.trim() || busy) return;
    setText(""); setMsgs((m) => [...m, { role: "user", text: t }]);
    const clean = Object.fromEntries(Object.entries(ov).filter(([, v]) => v !== "" && v != null));
    const p = await makePlan(t, clean);
    setMsgs((m) => [...m, p ? { role: "ai", plan: p } : { role: "ai", text: "I couldn't build that plan — see the error message." }]);
  };

  if (!project) return null;
  const ready = !!analysis;
  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {!ready && <div className="text-sm text-slate-500 p-4 text-center">Waiting for analysis to finish…</div>}
        {msgs.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === "user" ? "justify-end" : ""}`}>
            {m.role === "ai" && <div className="w-6 h-6 rounded-full bg-gradient-to-br from-accent to-fuchsia-500 grid place-items-center shrink-0 mt-0.5"><Bot size={13} /></div>}
            <div className={`rounded-xl px-3 py-2 text-sm max-w-[95%] ${m.role === "user" ? "bg-accent/20 border border-accent/30" : "bg-ink-800 border border-ink-600/60"}`}>
              {m.text && <div className="whitespace-pre-wrap">{m.text}</div>}
              {m.plan && <PlanCard plan={m.plan} latest={m.plan.plan_id === plan?.plan_id} onApply={async () => { onApply(); await startRender(); }} />}
            </div>
            {m.role === "user" && <div className="w-6 h-6 rounded-full bg-ink-600 grid place-items-center shrink-0 mt-0.5"><User size={13} /></div>}
          </div>))}
        {busy === "plan" && <div className="flex items-center gap-2 text-sm text-slate-400"><Loader2 className="animate-spin" size={14} /> Planning: scoring scenes, running A*, solving constraints…</div>}
        <div ref={end} />
      </div>
      <div className="p-3 border-t border-ink-700 space-y-2">
        {msgs.length <= 1 && ready && <div className="flex flex-wrap gap-1.5">{SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} className="chip hover:bg-ink-600 text-left">{s.length > 56 ? s.slice(0, 54) + "…" : s}</button>)}</div>}
        <button className="text-xs text-slate-400 flex items-center gap-1 hover:text-slate-200" onClick={() => setShowCfg(!showCfg)}><Sliders size={12} /> Editing configuration <ChevronDown size={12} className={showCfg ? "rotate-180" : ""} /></button>
        {showCfg && <ConfigEditor ov={ov} setOv={setOv} plan={plan} />}
        <div className="flex gap-2">
          <textarea className="input resize-none h-[58px]" placeholder="Describe the edit… e.g. “Make this a 30-second reel with subtitles”" value={text} disabled={!ready}
            onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
          <button className="btn-primary !px-3" disabled={!ready || !text.trim() || !!busy} onClick={() => send()}><Send size={16} /></button>
        </div>
      </div>
    </div>
  );
}

function ConfigEditor({ ov, setOv, plan }: { ov: Record<string, any>; setOv: (o: Record<string, any>) => void; plan: Plan | null }) {
  const set = (k: string, v: any) => setOv({ ...ov, [k]: v });
  const Sel = ({ k, opts, label }: { k: string; opts: string[]; label: string }) => (
    <div><div className="label mb-1">{label}</div><select className="input !py-1" value={ov[k] ?? ""} onChange={(e) => set(k, e.target.value || undefined)}><option value="">from prompt{plan ? ` (${plan.config[k]})` : ""}</option>{opts.map((o) => <option key={o}>{o}</option>)}</select></div>);
  return (
    <div className="panel p-3 grid grid-cols-2 gap-2 text-xs">
      <div><div className="label mb-1">Target seconds</div><input className="input !py-1" type="number" min={3} max={600} value={ov.target_duration ?? ""} placeholder="from prompt" onChange={(e) => set("target_duration", e.target.value ? Number(e.target.value) : undefined)} /></div>
      <Sel k="aspect_ratio" label="Aspect" opts={["9:16", "16:9", "1:1"]} /><Sel k="subtitle_style" label="Subtitle style" opts={["classic", "bold", "animated", "karaoke"]} />
      <Sel k="transition_style" label="Transitions" opts={["smooth", "fade", "none"]} /><Sel k="color_preset" label="Colour" opts={["none", "cinematic", "vivid", "bw"]} />
      <Sel k="sequencing" label="Sequencing" opts={["astar", "chronological"]} />
      <div><div className="label mb-1">Topic focus</div><input className="input !py-1" value={ov.topic ?? ""} placeholder="optional keywords" onChange={(e) => set("topic", e.target.value)} /></div>
      <label className="flex items-center gap-2 col-span-1"><input type="checkbox" checked={ov.remove_silence ?? true} onChange={(e) => set("remove_silence", e.target.checked)} /> Remove silence</label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={ov.subtitles ?? true} onChange={(e) => set("subtitles", e.target.checked)} /> Subtitles</label>
    </div>);
}

function PlanCard({ plan, latest, onApply }: { plan: Plan; latest: boolean; onApply: () => void }) {
  const { project, analysis } = useProject();
  const ok = plan.validation_status === "valid";
  const a = plan.algorithms;
  return (
    <div className="space-y-3 text-[13px]">
      <div className="flex items-center gap-2"><b>{ok ? "Editing plan ready" : "Plan could not be satisfied"}</b><StatusChip status={plan.validation_status} /></div>
      <div className="text-slate-300">
        {ok ? <>I selected <b>{plan.clips.length}</b> of <b>{analysis?.summary.scene_count}</b> scenes and built a <b>{plan.output.duration.toFixed(1)} s</b> {plan.output.aspect} edit ({plan.output.width}×{plan.output.height}), target {plan.config.target_duration} s ± {plan.config.duration_tolerance}.</>
          : <>No assignment of scene lengths satisfies every constraint, so nothing will be rendered.</>}
      </div>
      {ok && (<div><div className="label mb-1.5">Selected scenes (edit order)</div>
        <div className="flex flex-col gap-1.5">{plan.clips.map((c, i) => (
          <div key={c.scene_id} className="flex items-center gap-2 bg-ink-900 rounded-lg p-1.5">
            <img src={thumbUrl(project!.project_id, c.scene_id)} className="w-14 aspect-video object-cover rounded" alt="" />
            <div className="flex-1 min-w-0"><div className="text-xs font-medium">{i + 1}. Scene #{c.scene_id} · {c.duration.toFixed(1)} s</div>
              <div className="text-[10px] text-slate-500 truncate">{i > 0 ? (c.transition_in.duration > 0 ? `${c.transition_in.type} ${c.transition_in.duration}s in` : "hard cut in") : "opening"} · {c.segments.length} segment{c.segments.length > 1 ? "s" : ""}</div></div>
            <div className="text-xs font-bold" style={{ color: scoreColor(c.importance) }}>{c.importance.toFixed(0)}</div></div>))}</div></div>)}
      {plan.removed_scenes.length > 0 && (<div><div className="label mb-1">Removed scenes</div>
        <div className="text-[11px] text-slate-400 space-y-0.5">{plan.removed_scenes.slice(0, 8).map((r) => <div key={r.scene_id}>#{r.scene_id}: {r.reason}</div>)}{plan.removed_scenes.length > 8 && <div>+{plan.removed_scenes.length - 8} more</div>}</div></div>)}
      {plan.operations.length > 0 && (<div><div className="label mb-1">Editing operations</div>
        <ul className="text-[11px] text-slate-300 space-y-0.5 list-disc pl-4">{plan.operations.map((o, i) => <li key={i}><b className="text-slate-100">{o.op}</b> — {o.detail}</li>)}</ul></div>)}
      <div><div className="label mb-1">Constraint results</div>
        <div className="text-[11px] space-y-0.5">
          <div className="flex items-center gap-1">{a.csp.status === "satisfied" ? <CheckCircle2 size={12} className="text-lime-400" /> : <XCircle size={12} className="text-rose-400" />}CSP {a.csp.status} · {a.csp.nodes} nodes, {a.csp.backtracks} backtracks</div>
          <div className="flex items-center gap-1">{plan.validation.status === "valid" ? <CheckCircle2 size={12} className="text-lime-400" /> : <XCircle size={12} className="text-rose-400" />}Independent validation: {plan.validation.status}{plan.validation.checked ? ` (${plan.validation.checked} checks)` : ""}</div>
          {plan.validation.violations.map((v, i) => <div key={i} className="text-rose-300">✗ {v.constraint}: {v.message}</div>)}
          {plan.validation.suggestions?.map((s, i) => <div key={i} className="text-amber-300">→ {s}</div>)}
          {a.astar?.algorithm && <div className="text-slate-400">Sequencing: {a.astar.applied === "astar" ? "A*" : "chronological"} · cost {a.astar.cost} vs chronological {a.astar.chronological_cost}{a.astar.optimal ? "" : " (not guaranteed optimal)"}</div>}
        </div></div>
      {plan.warnings.map((w, i) => <div key={i} className="flex gap-1.5 text-[11px] text-amber-300"><AlertTriangle size={12} className="shrink-0 mt-0.5" />{w}</div>)}
      <div className="flex items-center justify-between pt-1"><span className="text-[11px] text-slate-500">Estimated render length: {ok ? fmt(plan.output.duration, true) : "—"}</span>
        <button className="btn-primary" disabled={!ok || !latest} onClick={onApply} title={!latest ? "A newer plan exists" : ""}>Apply edits</button></div>
    </div>);
}
