import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ListVideo, Pause, Play, SkipBack } from "lucide-react";
import { useProject } from "../../context/ProjectContext";
import { videoUrl } from "../../services/api";
import { ASPECT_CSS, fmt } from "../../utils/format";

type Mode = "source" | "plan" | "render";

export default function VideoPreview() {
  const { project, plan, jobs, currentTime, setCurrentTime, seekRequest } = useProject();
  const ref = useRef<HTMLVideoElement>(null);
  const [mode, setMode] = useState<Mode>("source");
  const [playing, setPlaying] = useState(false);
  const [showCrop, setShowCrop] = useState(true);
  const segIdx = useRef(0);
  const [localT, setLocalT] = useState(0);
  const [dur, setDur] = useState(0);

  const rendered = useMemo(() => jobs.find((j) => j.status === "completed" && j.download_url), [jobs]);
  const segments = useMemo(() => (plan?.renderable ? plan.clips.flatMap((c) => c.segments.map((s) => ({ ...s, focus: c.focus_x }))) : []), [plan]);
  const planTotal = useMemo(() => segments.reduce((a, s) => a + (s.end - s.start), 0), [segments]);
  const src = mode === "render" && rendered ? rendered.download_url! : project ? videoUrl(project.project_id) : "";

  useEffect(() => { if (ref.current && seekRequest.n > 0 && mode !== "render") { ref.current.currentTime = seekRequest.t; } }, [seekRequest, mode]);
  useEffect(() => { setPlaying(false); segIdx.current = 0; }, [mode]);

  const toggle = useCallback(() => {
    const v = ref.current; if (!v) return;
    if (v.paused) {
      if (mode === "plan" && segments.length) { segIdx.current = 0; v.currentTime = segments[0].start; }
      v.play();
    } else v.pause();
  }, [mode, segments]);

  const onTime = () => {
    const v = ref.current; if (!v) return;
    if (mode === "plan" && segments.length) {   // client-side playback of the plan on the ORIGINAL footage (no render needed)
      const s = segments[segIdx.current];
      if (s && v.currentTime >= s.end - 0.03) {
        if (segIdx.current + 1 < segments.length) { segIdx.current += 1; v.currentTime = segments[segIdx.current].start; } else { v.pause(); }
      }
      let acc = 0; for (let i = 0; i < segIdx.current; i++) acc += segments[i].end - segments[i].start;
      setLocalT(acc + Math.max(0, v.currentTime - (segments[segIdx.current]?.start ?? 0)));
      setCurrentTime(v.currentTime);
    } else { setLocalT(v.currentTime); if (mode === "source") setCurrentTime(v.currentTime); }
  };
  const total = mode === "plan" ? planTotal : dur;
  const aspect = mode === "render" && plan ? ASPECT_CSS[plan.output.aspect] : mode === "plan" && plan && showCrop ? ASPECT_CSS[plan.output.aspect] : undefined;
  const focus = mode === "plan" ? (segments[segIdx.current]?.focus ?? 0.5) : 0.5;

  if (!project) return null;
  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="flex items-center gap-2 px-3 py-2 text-xs">
        {([["source", "Source"], ["plan", "Plan preview"], ["render", "Rendered"]] as [Mode, string][]).map(([m, l]) => (
          <button key={m} disabled={(m === "plan" && !plan?.renderable) || (m === "render" && !rendered)} onClick={() => setMode(m)}
            className={`px-3 py-1 rounded-full font-medium disabled:opacity-30 ${mode === m ? "bg-accent text-white" : "bg-ink-700 text-slate-300"}`}>{l}</button>))}
        <span className="text-slate-500 ml-2">{mode === "plan" ? "Plays the planned segments from your original footage — no render needed" : mode === "render" ? "Latest exported/preview render" : "Original upload"}</span>
        {mode === "plan" && <label className="ml-auto flex items-center gap-1 text-slate-400"><input type="checkbox" checked={showCrop} onChange={(e) => setShowCrop(e.target.checked)} /> Aspect crop</label>}
      </div>
      <div className="flex-1 min-h-0 grid place-items-center bg-black/40 mx-3 rounded-xl overflow-hidden">
        <div className="h-full max-w-full flex items-center justify-center" style={{ aspectRatio: aspect }}>
          <video key={src} ref={ref} src={src} className="max-h-full max-w-full h-full w-full" style={{ objectFit: aspect ? "cover" : "contain", objectPosition: `${focus * 100}% 50%` }}
            onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onTimeUpdate={onTime} onLoadedMetadata={(e) => setDur(e.currentTarget.duration)} playsInline preload="metadata" />
        </div>
      </div>
      <div className="flex items-center gap-3 px-4 py-2.5">
        <button className="btn-ghost !px-2" onClick={() => { if (ref.current) { ref.current.currentTime = mode === "plan" ? segments[0]?.start ?? 0 : 0; segIdx.current = 0; } }}><SkipBack size={14} /></button>
        <button className="btn-primary !px-3" onClick={toggle}>{playing ? <Pause size={14} /> : <Play size={14} />}</button>
        <div className="font-mono text-xs text-slate-300 w-[132px] whitespace-nowrap">{fmt(localT, true)} / {fmt(total, true)}</div>
        <input type="range" className="flex-1 accent-violet-500" min={0} max={total || 1} step={0.05} value={Math.min(localT, total || 1)}
          onChange={(e) => {
            const t = Number(e.target.value); const v = ref.current; if (!v) return;
            if (mode === "plan") { let acc = 0; for (let i = 0; i < segments.length; i++) { const l = segments[i].end - segments[i].start; if (t <= acc + l) { segIdx.current = i; v.currentTime = segments[i].start + (t - acc); break; } acc += l; } }
            else v.currentTime = t;
          }} />
        {mode === "plan" && <span className="chip"><ListVideo size={12} /> {plan?.clips.length} clips</span>}
        {plan && <span className="chip">{plan.output.aspect} · {plan.output.width}×{plan.output.height}</span>}
      </div>
    </div>
  );
}
