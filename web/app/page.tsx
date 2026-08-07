import { brief, fmtDate, rankedSignals, stats } from "@/lib/data";
import { SignalRow, Trend } from "./components";

export default function Home() {
  const watch = new Set(brief?.watch ?? []);
  const notable = rankedSignals.filter((s) => !s.ai?.routine);
  const routine = rankedSignals.filter((s) => s.ai?.routine);
  const keepRate = stats.scanned ? (stats.kept / stats.scanned) * 100 : 0;

  return (
    <>
      <p className="eyebrow">
        {stats.from && `${fmtDate(stats.from)}–${fmtDate(stats.to)}`} · 중앙행정기관
        · {stats.days}일
      </p>

      <h1 className="headline">
        {brief?.headline ?? "정책 동향 리포트"}
      </h1>

      {brief ? (
        <p className="lead reading">{brief.overview}</p>
      ) : (
        <p className="lead reading">
          아직 종합 리포트가 없습니다.{" "}
          <code>python -m collector.brief</code>
        </p>
      )}

      <dl className="metrics">
        <div className="metric">
          <dt>수집 문서</dt>
          <dd>
            {stats.scanned.toLocaleString()}
            <small>건</small>
          </dd>
        </div>
        <div className="metric">
          <dt>분석 대상</dt>
          <dd>
            {stats.kept.toLocaleString()}
            <small>건 · {keepRate.toFixed(1)}%</small>
          </dd>
        </div>
        <div className="metric">
          <dt>도출 사안</dt>
          <dd>
            {rankedSignals.length}
            <small>개</small>
          </dd>
        </div>
        <div className="metric hl">
          <dt>주요 사안</dt>
          <dd>
            {notable.length}
            <small>개</small>
          </dd>
        </div>
      </dl>

      <Trend stats={stats} />

      {brief && brief.byCategory.length > 0 && (
        <section className="band">
          <h2>By category</h2>
          <p className="band-h">분야별</p>
          <dl className="cats">
            {brief.byCategory.map((c) => (
              <div className="cat" key={c.category}>
                <dt>{c.category}</dt>
                <dd>{c.note}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <section className="band">
        <h2>Signals</h2>
        <p className="band-h">주요 사안 {notable.length}건</p>
        <p className="band-note">
          여러 부처가 같은 사안의 문서를 동시에 생산한 순으로 정렬했습니다.
          각 항목의 <strong>근거 문서</strong>를 펼치면 원문 링크가 나옵니다.
        </p>

        {notable.length === 0 ? (
          <div className="empty">
            아직 사안이 없습니다.
            <br />
            <code>python -m collector.pipeline</code>
          </div>
        ) : (
          <div className="signals">
            {notable.map((s, i) => (
              <SignalRow
                key={s.id}
                s={s}
                rank={i + 1}
                watched={watch.has(s.id)}
              />
            ))}
          </div>
        )}
      </section>

      {routine.length > 0 && (
        <section className="band">
          <h2>Routine</h2>
          <p className="band-h">일상 행정업무 {routine.length}건</p>
          <p className="band-note">
            주기적으로 반복되는 정형 업무로 판정된 항목입니다. 참고용으로만
            둡니다.
          </p>
          <div className="signals">
            {routine.map((s, i) => (
              <SignalRow key={s.id} s={s} rank={i + 1} dim />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
