import axios from "axios";

export const http = axios.create({ baseURL: "/api", timeout: 120000 });

export interface VideoMeta { duration: number; width: number; height: number; fps: number; video_codec: string; audio_codec: string | null; has_audio: boolean }
export interface Summary { duration: number; scene_count: number; speech_duration: number | null; silence_duration: number | null; important_scenes: number; transcript_status: string; transcript_source: string; transcript_message: string }
export interface Project {
  project_id: string; project_name: string; original_filename: string | null; duration: number | null; status: string; stage: string; progress: number;
  error_message: string | null; created_at: string; has_video: boolean; has_music: boolean; metadata: VideoMeta | null;
  analysis_summary: Summary | null; transcript_status: string | null;
}
export interface Scene {
  scene_id: number; start: number; end: number; duration: number; transcript: string; speech_density: number | null; silence_pct: number | null; motion: number | null;
  importance: number; thumbnail: string | null; loudness_db: number | null; boundary_method: string;
  score_detail: { contributions: Record<string, number>; missing: string[]; weights_used: Record<string, number>; explanation: string };
}
export interface Analysis {
  metadata: VideoMeta; summary: Summary; silence: [number, number][]; activity: [number, number][]; timings: Record<string, number>; scene_notes: string[]; scenes: Scene[];
  transcript: { status: string; source: string; message: string; language: string | null; segments: { start: number; end: number; text: string }[] };
}
export interface Clip {
  scene_id: number; order: number; duration: number; segments: { start: number; end: number }[]; importance: number; focus_x: number; rationale: string;
  transition_in: { type: string; duration: number; discontinuity: number | null };
}
export interface Cue { start: number; end: number; text: string }
export interface RuleRec { rule_id: string; name: string; scope: string; target: string; condition: string; facts_evaluated: Record<string, unknown>; fired: boolean; recommendation: string; explanation: string }
export interface ProofNode { goal: string; proved: boolean; via: string; children: ProofNode[]; unmet_requirements?: string[] }
export interface AStar {
  algorithm: string; optimal: boolean; cost: number; expanded: number; generated: number; explored_states: number; seconds: number; note: string; applied: string;
  chronological_cost: number; improvement_vs_chronological: number; improvement_pct: number; order_scene_ids: number[]; chronological_scene_ids: number[]; candidate_ids: number[];
  trace: { step: number; path: number[]; g: number; h: number; f: number }[]; cost_notes?: string[];
}
export interface CSP {
  status: string; assignment: Record<string, any> | null; nodes: number; backtracks: number; pruned_values: number; seconds: number; failed_constraints: Record<string, number>;
  constraints: { name: string; description: string; scope: string[] }[]; trace: { var: string; value: any; consistent: boolean; violated: string | null; depth: number }[];
  diagnosis?: { suggestions: string[]; available_seconds: number };
}
export interface Plan {
  plan_id: string; project_id: string; validation_status: "valid" | "invalid" | "infeasible"; renderable: boolean; prompt: string;
  config: Record<string, any>; clips: Clip[]; removed_scenes: { scene_id: number; reason: string }[]; operations: { op: string; detail: string }[];
  output: { width: number; height: number; fps: number; duration: number; aspect: string }; subtitles: { enabled: boolean; requested?: boolean; position: string; style: string; cue_count: number };
  subtitle_cues: Cue[]; validation: { status: string; violations: { constraint: string; message: string }[]; checked?: number; suggestions?: string[] };
  warnings: string[]; stats?: { silence_intervals_removed: number; silence_seconds_removed: number }; planning_seconds: number;
  algorithms: { astar: AStar; csp: CSP; expert: { rules: RuleRec[]; facts?: Record<string, unknown>; backward: ProofNode | null } };
}
export interface Job {
  job_id: string; project_id: string; kind: "final" | "preview"; status: string; progress: number; stage: string; error_message: string | null;
  report: any; download_url: string | null; created_at: string;
}
export interface Decision { decision_id: number; phase: string; agent_name: string; decision: string; explanation: string; timestamp: string }

export const errText = (e: any): string => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d?.message) return d.message + (d.suggestions?.length ? " — " + d.suggestions.join("; ") : "");
  if (Array.isArray(d)) return d.map((x: any) => x.msg).join("; ");
  return e?.message ?? "Request failed";
};

export const api = {
  health: () => http.get("/health").then((r) => r.data),
  listProjects: () => http.get<Project[]>("/projects").then((r) => r.data),
  createProject: (project_name: string) => http.post<Project>("/projects", { project_name }).then((r) => r.data),
  getProject: (id: string) => http.get<Project>(`/projects/${id}`).then((r) => r.data),
  deleteProject: (id: string) => http.delete(`/projects/${id}`),
  upload: (id: string, file: File, onProgress?: (p: number) => void) => {
    const fd = new FormData(); fd.append("file", file);
    return http.post<Project>(`/upload`, fd, { params: { project_id: id }, timeout: 0, onUploadProgress: (e) => onProgress?.(e.total ? e.loaded / e.total : 0) }).then((r) => r.data);
  },
  uploadMusic: (id: string, file: File) => { const fd = new FormData(); fd.append("file", file); return http.post<Project>(`/projects/${id}/music`, fd).then((r) => r.data); },
  importSrt: (id: string, srt: string) => http.post(`/projects/${id}/transcript`, { srt }).then((r) => r.data),
  analyze: (id: string, force = false) => http.post(`/analyze/${id}`, null, { params: { force } }).then((r) => r.data),
  getAnalysis: (id: string) => http.get<Analysis>(`/analysis/${id}`).then((r) => r.data),
  createPlan: (id: string, prompt: string, overrides?: Record<string, any>) => http.post<Plan>(`/edit/${id}/plan`, { prompt, overrides }).then((r) => r.data),
  getPlan: (id: string) => http.get<Plan>(`/edit/${id}/plan`).then((r) => r.data),
  validate: (id: string) => http.post(`/edit/${id}/validate`).then((r) => r.data),
  preview: (id: string) => http.post<Job>(`/edit/${id}/preview`).then((r) => r.data),
  render: (id: string, exportOpts?: Record<string, any>) => http.post<Job>(`/render/${id}`, { export: exportOpts }).then((r) => r.data),
  jobStatus: (jobId: string) => http.get<Job>(`/render/${jobId}/status`).then((r) => r.data),
  jobs: (id: string) => http.get<Job[]>(`/projects/${id}/jobs`).then((r) => r.data),
  decisions: (id: string) => http.get<Decision[]>(`/agents/${id}/decisions`).then((r) => r.data),
  report: (id: string) => http.get(`/report/${id}`).then((r) => r.data),
};

export const videoUrl = (id: string) => `/api/projects/${id}/video`;
export const thumbUrl = (id: string, sceneId: number) => `/api/projects/${id}/thumbnails/${sceneId}`;
