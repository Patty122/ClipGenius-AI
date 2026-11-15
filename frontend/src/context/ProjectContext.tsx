import { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { Analysis, Decision, Job, Plan, Project, api, errText } from "../services/api";

interface Ctx {
  project: Project | null; analysis: Analysis | null; plan: Plan | null; jobs: Job[]; decisions: Decision[];
  currentTime: number; setCurrentTime: (t: number) => void; seekRequest: { t: number; n: number }; seekTo: (t: number) => void;
  busy: string | null; error: string | null; setError: (e: string | null) => void;
  refresh: () => Promise<void>; runAnalysis: (force?: boolean) => Promise<void>; makePlan: (prompt: string, overrides?: Record<string, any>) => Promise<Plan | null>;
  startRender: (opts?: Record<string, any>) => Promise<Job | null>; startPreview: () => Promise<Job | null>;
}
const C = createContext<Ctx>(null as unknown as Ctx);
export const useProject = () => useContext(C);

export function ProjectProvider({ projectId, children }: { projectId: string; children: ReactNode }) {
  const [project, setProject] = useState<Project | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [currentTime, setCurrentTime] = useState(0);
  const [seekRequest, setSeek] = useState({ t: 0, n: 0 });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const p = await api.getProject(projectId); setProject(p);
      if (p.analysis_summary) { try { setAnalysis(await api.getAnalysis(projectId)); } catch { /* not ready */ } } else setAnalysis(null);
      try { setPlan(await api.getPlan(projectId)); } catch { setPlan(null); }
      setJobs(await api.jobs(projectId)); setDecisions(await api.decisions(projectId));
    } catch (e) { setError(errText(e)); }
  }, [projectId]);
  useEffect(() => { refresh(); }, [refresh]);

  // poll while work is running: progress shown to the user is the backend's measured progress
  useEffect(() => {
    const active = project?.status === "analyzing" || jobs.some((j) => j.status === "queued" || j.status === "running");
    if (!active) return;
    const t = setInterval(refresh, 1000);
    return () => clearInterval(t);
  }, [project?.status, jobs, refresh]);

  const runAnalysis = useCallback(async (force = false) => {
    setBusy("analysis"); setError(null);
    try { await api.analyze(projectId, force); await refresh(); } catch (e) { setError(errText(e)); } finally { setBusy(null); }
  }, [projectId, refresh]);
  const makePlan = useCallback(async (prompt: string, overrides?: Record<string, any>) => {
    setBusy("plan"); setError(null);
    try { const p = await api.createPlan(projectId, prompt, overrides); setPlan(p); await refresh(); return p; }
    catch (e) { setError(errText(e)); return null; } finally { setBusy(null); }
  }, [projectId, refresh]);
  const startRender = useCallback(async (opts?: Record<string, any>) => {
    setError(null);
    try { const j = await api.render(projectId, opts); await refresh(); return j; } catch (e) { setError(errText(e)); return null; }
  }, [projectId, refresh]);
  const startPreview = useCallback(async () => {
    setError(null);
    try { const j = await api.preview(projectId); await refresh(); return j; } catch (e) { setError(errText(e)); return null; }
  }, [projectId, refresh]);
  const seekTo = useCallback((t: number) => { setSeek((s) => ({ t, n: s.n + 1 })); setCurrentTime(t); }, []);

  const value = useMemo(() => ({ project, analysis, plan, jobs, decisions, currentTime, setCurrentTime, seekRequest, seekTo, busy, error, setError, refresh, runAnalysis, makePlan, startRender, startPreview }),
    [project, analysis, plan, jobs, decisions, currentTime, seekRequest, seekTo, busy, error, refresh, runAnalysis, makePlan, startRender, startPreview]);
  return <C.Provider value={value}>{children}</C.Provider>;
}
