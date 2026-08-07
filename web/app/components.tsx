import { fmtDate, type Signal, type SourceDoc, type Stats } from "@/lib/data";

/** 신호 강도 1~5. 관측된 수치임을 보이려 항상 5칸으로 그린다. */
export function Meter({ n }: { n: number }) {
  return (
    <span className="meter" title={`신호 강도 ${n} / 5`}>
      {"▮".repeat(n)}
      <i>{"▮".repeat(Math.max(0, 5 - n))}</i>
    </span>
  );
}

/**
 * 일자별 수집량. 주말이 확 꺼지는 모양 자체가 정보다
 * (평일 4만 건 → 주말 1~2천 건).
 */
export function Trend({ stats }: { stats: Stats }) {
  const daily = stats.daily ?? [];
  if (daily.length < 2) return null;
  const max = Math.max(...daily.map((d) => d.scanned)) || 1;

  return (
    <section className="trend">
      <div className="trend-head">
        <h2>일자별 수집</h2>
        <span className="key">
          <i style={{ background: "var(--rule)" }} />
          훑음
          <i style={{ background: "var(--seal)", marginLeft: 12 }} />
          분석
        </span>
      </div>
      <div className="bars">
        {daily.map((d, i) => {
          const h = Math.max(2, (d.scanned / max) * 100);
          // 분석 대상은 1% 남짓이라 그대로 그리면 안 보인다. 최소 높이를 준다.
          const k = Math.max(3, (d.kept / max) * 100 * 6);
          return (
            <div className="col" key={d.date} title={`${d.date} · 훑음 ${d.scanned.toLocaleString()} · 분석 ${d.kept}`}>
              <div
                className="scan"
                style={{ height: `${h}%`, animationDelay: `${i * 60}ms` }}
              />
              <div className="kept" style={{ height: `${k}%` }} />
            </div>
          );
        })}
      </div>
      <div className="bars" style={{ height: "auto" }}>
        {daily.map((d) => (
          <div className="col" key={d.date}>
            <div className="cap">{d.date.slice(6)}</div>
          </div>
        ))}
      </div>
    </section>
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
 * 사안 하나. 페이지 이동 없이 한자리에서 다 읽힌다.
 * 근거 문서만 접어 둔다 — 사안당 수십 건이라 펼쳐두면 리포트가 아니라 목록이 된다.
 */
export function SignalRow({
  s,
  rank,
  watched = false,
  dim = false,
}: {
  s: Signal;
  rank: number;
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
      className={`signal${watched ? " watch" : ""}${dim ? " dim" : ""}`}
      style={{ animationDelay: `${Math.min(rank, 12) * 45}ms` }}
    >
      <div className="rank">{String(rank).padStart(2, "0")}</div>

      <div className="body">
        <div className="tags">
          {s.ai?.category && <span className="tag">{s.ai.category}</span>}
          <span className="tag kw">{s.keyword}</span>
          <Meter n={s.strength} />
          <span className="count">
            {s.orgCount}개 기관 · {s.docCount}건
          </span>
          {watched && <span className="tag watch">눈여겨볼 사안</span>}
        </div>

        <h3>{s.ai?.title || s.title}</h3>

        {s.ai?.summary && <p className="sum">{s.ai.summary}</p>}

        {s.ai?.impact && s.ai.impact !== "불명확" && (
          <p className="impact">
            <b>영향</b> {s.ai.impact}
          </p>
        )}

        <p className="orgline">
          {fmtDate(s.periodFrom)}
          {s.periodFrom !== s.periodTo && `–${fmtDate(s.periodTo)}`} ·{" "}
          {s.orgs.join(" · ")}
        </p>

        <details className="ev">
          <summary>
            <span className="caret">▸</span> 근거 문서 {s.docCount}건
          </summary>

          <div className="ev-body">
            {s.sharedTerms.length > 0 && (
              <div className="terms">
                {s.sharedTerms.map((t) => (
                  <span className="term" key={t}>
                    {t}
                  </span>
                ))}
              </div>
            )}

            {groups.map(([org, docs]) => (
              <div className="org-grp" key={org}>
                <div className="org-name">
                  {org} <span>{docs.length}건</span>
                </div>
                {docs.map((d, i) => (
                  <div className="doc" key={i}>
                    <a
                      href={sourceUrl(d)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {d.title}
                    </a>
                    <span className="m">
                      {fmtDate(d.date)}
                      {d.dept ? ` · ${d.dept}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            ))}

            {s.ai && (
              <p className="ai-note">
                ⓘ 위 요약은 {s.ai.model}이 <b>문서 제목만</b> 보고 쓴 초안입니다.
                제목 밖의 사실은 알 수 없으며 틀릴 수 있습니다.
              </p>
            )}
          </div>
        </details>
      </div>
    </article>
  );
}
