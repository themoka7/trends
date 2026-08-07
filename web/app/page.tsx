import { brief, fmtDate, rankedSignals, stats } from "@/lib/data";
import { SignalCard } from "./components";

export default function Home() {
  const watch = new Set(brief?.watch ?? []);
  const notable = rankedSignals.filter((s) => !s.ai?.routine);
  const routine = rankedSignals.filter((s) => s.ai?.routine);

  return (
    <>
      {/* ── 1장짜리 리포트 헤더 ─────────────────────────────── */}
      <section className="mb-10">
        <p className="font-mono text-xs text-stone-500 dark:text-stone-400">
          {stats.from && `${fmtDate(stats.from)}~${fmtDate(stats.to)}`} ·{" "}
          중앙행정기관
        </p>

        {brief ? (
          <>
            <h1 className="mt-2 text-2xl font-semibold leading-snug tracking-tight sm:text-[28px]">
              {brief.headline}
            </h1>
            <p className="mt-4 whitespace-pre-line text-[15px] leading-relaxed text-stone-700 dark:text-stone-300">
              {brief.overview}
            </p>
          </>
        ) : (
          <>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">
              정책 동향 리포트
            </h1>
            <p className="mt-3 text-sm text-stone-500">
              아직 종합 리포트가 없습니다.{" "}
              <code className="font-mono text-xs">
                python -m collector.brief
              </code>
            </p>
          </>
        )}

        <dl className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-stone-200 sm:grid-cols-4 dark:bg-stone-800">
          {[
            ["수집 문서", stats.scanned.toLocaleString(), "건"],
            ["분석 대상", stats.kept.toLocaleString(), "건"],
            ["도출 사안", String(rankedSignals.length), "개"],
            ["주요 사안", String(notable.length), "개"],
          ].map(([k, v, u]) => (
            <div key={k} className="bg-white p-4 dark:bg-stone-900">
              <dt className="text-xs text-stone-500 dark:text-stone-400">{k}</dt>
              <dd className="mt-0.5 font-mono text-xl font-semibold tabular-nums">
                {v}
                <span className="ml-0.5 text-xs font-normal text-stone-500">
                  {u}
                </span>
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* ── 분야별 총평 ────────────────────────────────────── */}
      {brief && brief.byCategory.length > 0 && (
        <section className="mb-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
            분야별
          </h2>
          <div className="divide-y divide-stone-200 overflow-hidden rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
            {brief.byCategory.map((c) => (
              <div key={c.category} className="flex gap-4 p-4">
                <span className="w-20 shrink-0 text-sm font-semibold">
                  {c.category}
                </span>
                <span className="text-sm leading-relaxed text-stone-700 dark:text-stone-300">
                  {c.note}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── 사안 전체 (클릭 없이 다 보인다) ──────────────────── */}
      <section className="mb-10">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
          주요 사안 {notable.length}건
        </h2>
        <p className="mb-4 text-xs text-stone-500 dark:text-stone-400">
          각 항목의 <strong>근거 문서</strong>를 펼치면 원문 링크가 나옵니다.
        </p>
        <ul className="space-y-3">
          {notable.map((s) => (
            <li key={s.id}>
              <SignalCard s={s} watched={watch.has(s.id)} />
            </li>
          ))}
        </ul>
      </section>

      {routine.length > 0 && (
        <section>
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-stone-500 dark:text-stone-400">
            일상 행정업무 {routine.length}건
          </h2>
          <p className="mb-4 text-xs text-stone-500 dark:text-stone-400">
            주기적으로 반복되는 정형 업무로 판정된 항목입니다.
          </p>
          <ul className="space-y-3">
            {routine.map((s) => (
              <li key={s.id}>
                <SignalCard s={s} dim />
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
