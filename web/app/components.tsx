import { fmtDate, type Signal, type SourceDoc } from "@/lib/data";

/** 신호 강도 1~5. 추론이 아니라 관측된 수치임을 보이기 위해 항상 5칸으로 그린다. */
export function Strength({ n }: { n: number }) {
  return (
    <span
      className="font-mono text-[13px] leading-none tracking-tight text-stone-500 dark:text-stone-400"
      title={`신호 강도 ${n} / 5`}
    >
      {"●".repeat(n)}
      <span className="text-stone-300 dark:text-stone-700">
        {"○".repeat(Math.max(0, 5 - n))}
      </span>
    </span>
  );
}

/** open.go.kr 원문 상세 링크. 식별자가 없으면 목록으로 보낸다. */
function sourceUrl(d: SourceDoc) {
  if (d.doc_key && d.produced_at) {
    const q = new URLSearchParams({
      prdnNstRgstNo: d.doc_key,
      prdnDt: d.produced_at,
      nstSeCd: "C",
    });
    return `https://www.open.go.kr/othicInfo/infoList/infoListDetl2.do?${q}`;
  }
  return "https://www.open.go.kr/othicInfo/infoList/infoList.do";
}

/**
 * 사안 카드. 페이지 이동 없이 한자리에서 다 읽을 수 있게 한다.
 * 근거 문서만 <details> 로 접어 둔다 — 목록이 길어 스크롤을 잡아먹기 때문.
 */
export function SignalCard({
  s,
  watched = false,
  dim = false,
}: {
  s: Signal;
  watched?: boolean;
  dim?: boolean;
}) {
  const byOrg = new Map<string, SourceDoc[]>();
  for (const d of s.sourceDocs) {
    if (!byOrg.has(d.org)) byOrg.set(d.org, []);
    byOrg.get(d.org)!.push(d);
  }
  const groups = [...byOrg.entries()].sort((a, b) => b[1].length - a[1].length);

  return (
    <article
      className={`rounded-xl border bg-white p-5 dark:bg-stone-900 ${
        watched
          ? "border-stone-900 dark:border-stone-300"
          : "border-stone-200 dark:border-stone-800"
      } ${dim ? "opacity-70" : ""}`}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        {s.ai?.category && (
          <span className="rounded bg-stone-900 px-2 py-0.5 font-medium text-white dark:bg-stone-100 dark:text-stone-900">
            {s.ai.category}
          </span>
        )}
        <span className="rounded bg-stone-100 px-2 py-0.5 text-stone-600 dark:bg-stone-800 dark:text-stone-400">
          {s.keyword}
        </span>
        <Strength n={s.strength} />
        <span className="font-mono text-stone-500 dark:text-stone-400">
          {s.orgCount}개 기관 · {s.docCount}건
        </span>
        {watched && (
          <span className="ml-auto rounded bg-stone-900 px-2 py-0.5 text-white dark:bg-stone-100 dark:text-stone-900">
            눈여겨볼 사안
          </span>
        )}
      </div>

      <h3 className="text-[15px] font-semibold leading-snug">
        {s.ai?.title || s.title}
      </h3>

      {s.ai?.summary && (
        <p className="mt-2 text-sm leading-relaxed text-stone-700 dark:text-stone-300">
          {s.ai.summary}
        </p>
      )}

      {s.ai?.impact && s.ai.impact !== "불명확" && (
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">
          <span className="font-medium text-stone-800 dark:text-stone-200">
            영향 대상
          </span>{" "}
          · {s.ai.impact}
        </p>
      )}

      <p className="mt-3 font-mono text-xs text-stone-500 dark:text-stone-500">
        {fmtDate(s.periodFrom)}
        {s.periodFrom !== s.periodTo && `~${fmtDate(s.periodTo)}`} ·{" "}
        {s.orgs.join(", ")}
      </p>

      <details className="group mt-3 border-t border-stone-100 pt-3 dark:border-stone-800">
        <summary className="cursor-pointer list-none text-xs font-medium text-stone-600 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100">
          <span className="inline-block transition group-open:rotate-90">▸</span>{" "}
          근거 문서 {s.docCount}건 보기
        </summary>

        <div className="mt-3 space-y-3">
          {s.sharedTerms.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {s.sharedTerms.map((t) => (
                <span
                  key={t}
                  className="rounded bg-stone-100 px-1.5 py-0.5 text-[11px] text-stone-600 dark:bg-stone-800 dark:text-stone-400"
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          {groups.map(([org, docs]) => (
            <div key={org}>
              <div className="mb-1 text-xs font-semibold text-stone-700 dark:text-stone-300">
                {org}{" "}
                <span className="font-mono font-normal text-stone-400">
                  {docs.length}건
                </span>
              </div>
              <ul className="space-y-1 border-l-2 border-stone-100 pl-3 dark:border-stone-800">
                {docs.map((d, i) => (
                  <li key={i} className="text-xs leading-relaxed">
                    <a
                      href={sourceUrl(d)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline"
                    >
                      {d.title}
                    </a>
                    <span className="ml-1.5 font-mono text-stone-400">
                      {fmtDate(d.date)}
                      {d.dept ? ` · ${d.dept}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {s.ai && (
            <p className="pt-1 text-[11px] leading-relaxed text-stone-500 dark:text-stone-500">
              ⓘ 위 요약은 {s.ai.model}이 <strong>문서 제목만</strong> 보고 쓴
              초안입니다. 제목 밖의 사실은 알 수 없으며 틀릴 수 있습니다.
            </p>
          )}
        </div>
      </details>
    </article>
  );
}
