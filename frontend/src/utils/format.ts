export const fmt = (t: number | null | undefined, ms = false) => {
  if (t == null || Number.isNaN(t)) return "—";
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${m}:${s.toFixed(ms ? 1 : 0).padStart(ms ? 4 : 2, "0")}`;
};
export const pct = (x: number | null | undefined, d = 0) => (x == null ? "—" : `${(x * 100).toFixed(d)}%`);
export const scoreColor = (s: number) => (s >= 70 ? "#a3e635" : s >= 45 ? "#fbbf24" : "#fb7185");
export const ASPECT_CSS: Record<string, string> = { "9:16": "9 / 16", "16:9": "16 / 9", "1:1": "1 / 1" };
