import { useEffect, useMemo, useRef, useState } from "react";
import { Minus, Plus } from "lucide-react";
import { useProject } from "../../context/ProjectContext";
import { thumbUrl } from "../../services/api";
import { fmt, scoreColor } from "../../utils/format";

const LABEL_W = 92;

export default function Timeline() {
  const { project, analysis, plan, currentTime, seekTo } = useProject();
  const [pps, setPps] = useState(12);                      // pixels per second (zoom)
  const scroller = useRef<HTMLDivElement>(null);
  const dur = analysis?.summary.duration ?? project?.duration ?? 0;
  useEffect(() => {   // fit the whole video into the visible width on load / when the duration changes
    const w = scroller.current?.clientWidth ?? 0;
    if (dur > 0 && w > 0) setPps(Math.max(3, Math.min(120, (w - LABEL_W - 28) / dur)));
  }, [dur]);
  const W = Math.max(300, dur * pps);
  const selected = useMemo(() => new Set(plan?.clips.map((c) => c.scene_id) ?? []), [plan]);
  const ticks = useMemo(() => { const step = pps > 40 ? 1 : pps > 18 ? 5 : pps > 8 ? 10 : 30; return Array.from({ length: Math.floor(dur / step) + 1 }, (_, i) => i * step); }, [dur, pps]);

  const click = (e: React.MouseEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    seekTo(Math.max(0, Math.min(dur, (e.clientX - r.left) / pps)));
  };
  if (!project) return null;
  const editW = Math.max(300, (plan?.output.duration ?? 0) * pps);
  const outStarts = (() => { let run = 0; return (plan?.clips ?? []).map((c, i) => { const s = i === 0 ? 0 : Math.max(0, run - c.transition_in.duration); run = s + c.duration; return s; }); })();

  return (
    <div className="h-full flex flex-col bg-ink-900 border-t border-ink-600/60 min-h-0">
      <div className="flex items-center gap-3 px-3 py-1.5 text-xs border-b border-ink-700">
        <span className="label">Timeline</span><span className="font-mono text-slate-400">{fmt(currentTime, true)} / {fmt(dur)}</span>
        <span className="chip"><span className="w-2 h-2 rounded-sm bg-lime-400" /> selected</span><span className="chip"><span className="w-2 h-2 rounded-sm bg-cyan-400/70" /> audio</span><span className="chip"><span className="w-2 h-2 rounded-sm bg-rose-400/50" /> silence</span>
        <div className="ml-auto flex items-center gap-1"><button className="btn-ghost !px-1.5 !py-0.5" onClick={() => setPps((p) => Math.max(3, p / 1.4))}><Minus size={12} /></button>
          <span className="text-slate-500 w-14 text-center">{pps.toFixed(0)} px/s</span>
          <button className="btn-ghost !px-1.5 !py-0.5" onClick={() => setPps((p) => Math.min(120, p * 1.4))}><Plus size={12} /></button></div>
      </div>
      <div ref={scroller} className="flex-1 overflow-auto relative min-h-0">
        <div style={{ width: W + LABEL_W + 40 }} className="relative pb-2">
          <div className="flex h-5 sticky top-0 z-20 bg-ink-900">
            <div style={{ width: LABEL_W }} className="shrink-0 sticky left-0 bg-ink-900 z-30" />
            <div className="relative" style={{ width: W }} onClick={click}>{ticks.map((t) => <div key={t} className="absolute top-0 text-[10px] text-slate-500 border-l border-ink-600 pl-1 h-5" style={{ left: t * pps }}>{fmt(t)}</div>)}</div>
          </div>
          <Row label="Video" h={52}>
            <div className="relative h-full" style={{ width: W }} onClick={click}>
              {analysis?.scenes.map((s) => { const sel = selected.has(s.scene_id); return (
                <div key={s.scene_id} className={`absolute top-0 h-full rounded-md overflow-hidden border ${sel ? "border-lime-400" : "border-ink-500 opacity-60"}`} style={{ left: s.start * pps, width: Math.max(2, (s.end - s.start) * pps - 2) }}
                  title={`Scene ${s.scene_id} · ${fmt(s.start, true)}–${fmt(s.end, true)} · importance ${s.importance.toFixed(0)}\n${s.score_detail.explanation}`}>
                  <img src={thumbUrl(project.project_id, s.scene_id)} className="absolute inset-0 w-full h-full object-cover opacity-50" alt="" loading="lazy" />
                  <div className="relative px-1.5 py-0.5 text-[10px] font-semibold flex justify-between"><span>#{s.scene_id}</span><span style={{ color: scoreColor(s.importance) }}>{s.importance.toFixed(0)}</span></div>
                  {sel && <div className="absolute bottom-0 left-0 right-0 h-1 bg-lime-400" />}</div>); })}
            </div>
          </Row>
          <Row label="Audio" h={30}>
            <div className="relative h-full" style={{ width: W }} onClick={click}>
              {analysis?.activity.map(([a, b], i) => <div key={"a" + i} className="absolute top-1 bottom-1 rounded bg-cyan-400/60" style={{ left: a * pps, width: Math.max(1, (b - a) * pps) }} />)}
              {analysis?.silence.map(([a, b], i) => <div key={"s" + i} className="absolute top-1 bottom-1 rounded bg-rose-400/30 border border-rose-400/40" style={{ left: a * pps, width: Math.max(1, (b - a) * pps) }} title={`silence ${fmt(a, true)}–${fmt(b, true)}`} />)}
            </div>
          </Row>
          <Row label="Transcript" h={28}>
            <div className="relative h-full" style={{ width: W }} onClick={click}>
              {analysis?.transcript.segments.map((s, i) => <div key={i} className="absolute top-1 bottom-1 px-1 text-[10px] truncate rounded bg-amber-400/25 text-amber-200 border border-amber-400/30 leading-5" style={{ left: s.start * pps, width: Math.max(2, (s.end - s.start) * pps) }} title={s.text}>{s.text}</div>)}
              {analysis && analysis.transcript.segments.length === 0 && <div className="text-[11px] text-slate-500 leading-7 pl-2">No transcript ({analysis.transcript.status}) — import an SRT or install Whisper</div>}
            </div>
          </Row>
          <div className="mx-3 my-1.5 border-t border-dashed border-ink-600" />
          <Row label="Edit (output)" h={40}>
            <div className="relative h-full" style={{ width: editW }}>
              {plan?.clips.map((c, i) => (
                <div key={c.scene_id} className="absolute top-0 h-full rounded-md bg-gradient-to-r from-violet-600/70 to-fuchsia-600/60 border border-violet-300/40 px-1.5 text-[10px] font-semibold overflow-hidden"
                  style={{ left: outStarts[i] * pps, width: Math.max(2, c.duration * pps - 1) }} title={c.rationale}>
                  #{c.scene_id} · {c.duration.toFixed(1)}s{c.transition_in.duration > 0 && <span className="absolute left-0 top-0 bottom-0 bg-white/30" style={{ width: c.transition_in.duration * pps }} title={`${c.transition_in.type} ${c.transition_in.duration}s`} />}</div>))}
              {!plan && <div className="text-[11px] text-slate-500 leading-10 pl-2">Ask the AI assistant to plan an edit</div>}
            </div>
          </Row>
          <Row label="Subtitles" h={24}>
            <div className="relative h-full" style={{ width: editW }}>
              {plan?.subtitle_cues.map((c, i) => <div key={i} className="absolute top-0.5 bottom-0.5 rounded bg-sky-400/30 border border-sky-300/40 text-[9px] truncate px-1 leading-4" style={{ left: c.start * pps, width: Math.max(2, (c.end - c.start) * pps) }} title={c.text}>{c.text}</div>)}
            </div>
          </Row>
          <div className="absolute top-0 bottom-0 w-px bg-accent pointer-events-none z-10" style={{ left: LABEL_W + currentTime * pps }}><div className="w-2.5 h-2.5 -ml-[5px] bg-accent rounded-sm" /></div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, h, children }: { label: string; h: number; children: React.ReactNode }) {
  return (<div className="flex mt-1" style={{ height: h }}>
    <div style={{ width: LABEL_W }} className="shrink-0 sticky left-0 z-20 bg-ink-900 text-[10px] uppercase tracking-wider text-slate-500 font-semibold px-3 flex items-center">{label}</div>
    <div className="bg-ink-850/60 rounded">{children}</div></div>);
}
