import feed from "@/public/feed.json";

/**
 * 데이터 계층 — 배치가 만든 JSON을 빌드 시점에 읽는다.
 *
 * GitHub Pages 는 정적 호스팅이라 서버에서 DB를 읽을 수 없다.
 * `python -m collector.export` 가 public/feed.json 을 갱신하고,
 * Actions 가 그걸 커밋하면 재빌드되어 사이트에 반영된다.
 */

export type SourceDoc = {
  date: string;
  org: string;
  dept: string;
  title: string;
  doc_key?: string;
  produced_at?: string;
};

export type Ai = {
  title: string;
  summary: string;
  impact: string;
  category: string;
  routine: boolean;
  notability: number;
  model: string;
  generatedAt: string;
};

export type Signal = {
  id: string;
  keyword: string;
  sharedTerms: string[];
  cohesion: number;
  title: string;
  summary: string;
  strength: number;
  docCount: number;
  orgCount: number;
  orgs: string[];
  sourceDocs: SourceDoc[];
  periodFrom: string;
  periodTo: string;
  published: boolean;
  ai: Ai | null;
};

export type Brief = {
  headline: string;
  overview: string;
  byCategory: { category: string; note: string }[];
  watch: string[];
  periodFrom: string;
  periodTo: string;
  model: string;
  generatedAt: string;
};

export type Stats = {
  days: number;
  scanned: number;
  kept: number;
  from: string;
  to: string;
  /** 일자별 추이. 주말이 꺼지는 모양 자체가 정보다. */
  daily?: { date: string; scanned: number; kept: number }[];
};

const data = feed as unknown as {
  brief: Brief | null;
  stats: Stats;
  signals: Signal[];
};

export const brief = data.brief;
export const stats = data.stats;
export const signals = data.signals;

/** 일상 업무로 판정된 것을 뒤로 민다. */
export const rankedSignals = [...signals].sort((a, b) => {
  const ra = a.ai?.routine ? 1 : 0;
  const rb = b.ai?.routine ? 1 : 0;
  if (ra !== rb) return ra - rb;
  const na = a.ai?.notability ?? 0;
  const nb = b.ai?.notability ?? 0;
  if (na !== nb) return nb - na;
  return b.cohesion - a.cohesion;
});

export function getSignal(id: string) {
  return signals.find((s) => s.id === id) ?? null;
}

export function fmtDate(d: string) {
  return d ? `${d.slice(4, 6)}/${d.slice(6)}` : "";
}
