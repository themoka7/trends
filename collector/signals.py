"""신호 탐지 — 통계로 근거를 만든다. AI는 나중에 해석만 붙인다.

기획서 §Ⅲ-3-2 의 원칙:
    제목 하나 보고 "정부가 X를 준비 중"이라 단정하면 반드시 틀린다.
    통계적 근거를 코드로 먼저 뽑고, AI는 그 클러스터에 이름을 붙이고
    맥락을 설명하는 역할만 한다.

    python -m collector.signals --days 7
    python -m collector.signals --days 7 --min-orgs 2 --top 25
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .db import Store

# 어느 문서에나 붙는 행정 상용어. 이런 키워드로 묶으면 의미 없는 덩어리가 나온다.
# 데이터 기반 IDF로도 걸러지지만, 명백한 것은 먼저 뺀다.
STOPWORDS = {
    # 행정 상용어
    "계획", "보고", "요청", "결과", "추진", "검토", "제출", "회신", "알림",
    "개최", "관련", "사업", "운영", "관리", "실시", "통보", "안내", "협조",
    "변경", "승인", "신청", "처리", "업무", "자료", "현황", "내역", "지원",
    "확인", "조회", "의뢰", "송부", "공유", "참석", "제작", "작성", "시행",
    # 문서 유형 — 주제가 아니다. 이걸로 묶으면 무관한 문서가 한 덩어리가 된다.
    "추진계획", "기본계획", "시행계획", "종합계획", "실행계획", "수립",
    "실태조사", "연구", "연구용역", "용역", "과제", "평가", "심의", "자문",
    "위원회", "협의회", "간담회", "회의", "교육", "훈련", "점검", "조사",
}


@dataclass
class Cluster:
    keyword: str
    docs: list = field(default_factory=list)

    @property
    def orgs(self) -> set[str]:
        return {d["org"] for d in self.docs}

    @property
    def dates(self) -> set[str]:
        return {d["date"] for d in self.docs}

    @property
    def cohesion_keywords(self) -> list[str]:
        """문서 절반 이상이 공유하는 키워드 (묶은 키워드 자신은 제외).

        좋은 클러스터와 나쁜 클러스터를 가르는 결정적 지표다. 실측:
          · 「컴퓨팅」 — 4건이 '클라우드·시행계획·제출'을 공유 → 같은 사안
          · 「마련」   — 8건이 공유하는 것이 없음 → 서로 무관한 문서 더미
        """
        n = len(self.docs)
        if n < 2:
            return []
        cnt: Counter[str] = Counter()
        for d in self.docs:
            for kw in set(d["keywords"]):
                if kw != self.keyword and kw not in STOPWORDS and len(kw) > 1:
                    cnt[kw] += 1
        return [k for k, c in cnt.most_common() if c >= n * 0.5]

    @property
    def cohesion(self) -> int:
        return len(self.cohesion_keywords)

    @property
    def score(self) -> float:
        """응집도를 가장 크게 본다.

        기관 수만 보면 「추진계획」처럼 아무 관계 없는 문서가 14개 기관에
        걸쳐 있다는 이유로 1위가 된다. 그것은 신호가 아니다.
        """
        return (
            self.cohesion * 4.0
            + len(self.orgs) * 2.0
            + math.log1p(len(self.docs))
            + self._idf
        )

    _idf: float = 0.0


def build_idf(store: Store, dates: list[str]) -> dict[str, float]:
    """전건(38k/일) 키워드 빈도로 희소성을 잰다.

    통과분(380/일)이 아니라 **전건**으로 재는 것이 중요하다.
    흔한 행정 용어인지 아닌지는 전체 분포가 말해준다.
    """
    q = ",".join("?" * len(dates))
    rows = store.conn.execute(
        f"SELECT keyword, SUM(cnt) c FROM keyword_daily "
        f"WHERE date IN ({q}) GROUP BY keyword", dates
    ).fetchall()
    total = sum(r["c"] for r in rows) or 1
    return {r["keyword"]: math.log(total / r["c"]) for r in rows}


def load_docs(store: Store, dates: list[str]) -> list[dict]:
    q = ",".join("?" * len(dates))
    rows = store.conn.execute(
        f"SELECT doc_key, date, title, org, dept, unit_job, produced_at, keywords "
        f"FROM docs WHERE date IN ({q})", dates
    ).fetchall()
    return [
        {"doc_key": r["doc_key"], "date": r["date"], "title": r["title"],
         "org": r["org"], "dept": r["dept"], "unit_job": r["unit_job"],
         "produced_at": r["produced_at"],
         "keywords": [k for k in (r["keywords"] or "").split("\n") if k]}
        for r in rows
    ]


def common_keywords(idf: dict[str, float], cut: float) -> set[str]:
    """전건 기준으로 가장 흔한 상위 `cut` 비율의 키워드.

    이것을 빼지 않으면 「추진계획」「기본계획」「실태조사」처럼
    **주제가 아니라 문서 유형**인 단어로 클러스터가 만들어진다.
    실측: 14개 기관이 「추진계획」을 공유하지만 내용은 개인정보 영향평가,
    공익광고, 안전점검의 날, 외국인 밀집지역 관리로 서로 무관했다.

    STOPWORDS 를 손으로 늘리는 것은 끝이 없다. 분포로 자른다.
    """
    if cut <= 0:
        return set()
    ranked = sorted(idf.items(), key=lambda kv: kv[1])  # idf 낮은 순 = 흔한 순
    n = max(1, int(len(ranked) * cut))
    return {k for k, _ in ranked[:n]}


def build_clusters(
    docs: list[dict], idf: dict[str, float], min_orgs: int, min_docs: int,
    banned: set[str] | None = None,
) -> list[Cluster]:
    """키워드별로 통과 문서를 묶는다.

    '여러 기관이 같은 주제를 동시에 다루고 있다' 가 가장 강한 신호다.
    """
    banned = banned or set()
    by_kw: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        for kw in set(d["keywords"]):
            if len(kw) < 2 or kw in STOPWORDS or kw in banned:
                continue
            by_kw[kw].append(d)

    out = []
    for kw, ds in by_kw.items():
        c = Cluster(kw, ds)
        c._idf = idf.get(kw, 0.0)
        if len(c.orgs) >= min_orgs and len(ds) >= min_docs:
            out.append(c)
    return sorted(out, key=lambda c: c.score, reverse=True)


def find_spikes(store: Store, dates: list[str], factor: float = 3.0,
                min_recent: int = 5) -> list[dict]:
    """전건 기준 키워드 급증. 마지막 날 vs 그 이전 평균.

    ⚠️ 7일 표본에서는 기준선이 얇다. 파일럿에서는 참고 지표로만 본다.
    """
    if len(dates) < 3:
        return []
    recent, base = dates[-1], dates[:-1]
    qb = ",".join("?" * len(base))
    prev = {
        r["keyword"]: r["c"] / len(base)
        for r in store.conn.execute(
            f"SELECT keyword, SUM(cnt)*1.0 c FROM keyword_daily "
            f"WHERE date IN ({qb}) GROUP BY keyword", base
        )
    }
    out = []
    for r in store.conn.execute(
        "SELECT keyword, SUM(cnt) c FROM keyword_daily WHERE date=? GROUP BY keyword",
        (recent,),
    ):
        kw, now = r["keyword"], r["c"]
        if kw in STOPWORDS or len(kw) < 2 or now < min_recent:
            continue
        avg = prev.get(kw, 0.0)
        if avg == 0:
            out.append({"keyword": kw, "now": now, "avg": 0.0,
                        "ratio": float("inf"), "kind": "신규등장"})
        elif now / avg >= factor:
            out.append({"keyword": kw, "now": now, "avg": avg,
                        "ratio": now / avg, "kind": "급증"})
    return sorted(out, key=lambda x: (x["ratio"], x["now"]), reverse=True)


def report(clusters: list[Cluster], spikes: list[dict], top: int) -> None:
    print(f"\n{'='*74}\n동시다발 클러스터  상위 {top}\n{'='*74}")
    if not clusters:
        print("  (없음 — 기관 수 조건을 낮춰 보라)")
    for i, c in enumerate(clusters[:top], 1):
        co = c.cohesion_keywords[:5]
        print(f"\n[{i}] 「{c.keyword}」  "
              f"기관 {len(c.orgs)} · 문서 {len(c.docs)} · 일자 {len(c.dates)} "
              f"· 응집 {c.cohesion} · 점수 {c.score:.1f}")
        if co:
            print(f"    공유어: {' · '.join(co)}")
        print(f"    기관: {', '.join(sorted(c.orgs))[:90]}")
        for d in c.docs[:4]:
            print(f"      · [{d['date'][4:]}] {d['org'][:6]:<7} {d['title'][:58]}")
        if len(c.docs) > 4:
            print(f"      … 외 {len(c.docs)-4}건")

    print(f"\n{'='*74}\n키워드 급증 / 신규등장  상위 20  (전건 기준)\n{'='*74}")
    if not spikes:
        print("  (없음)")
    for s in spikes[:20]:
        r = "신규" if s["ratio"] == float("inf") else f"{s['ratio']:.1f}배"
        print(f"  {s['kind']:<6} 「{s['keyword'][:20]:<20}」 "
              f"{s['now']:>5}건  (평소 {s['avg']:>6.1f})  {r}")


def strength_of(c: Cluster) -> int:
    """1~5 정수. 0이나 소수점은 저장이 실패한다(기획서 Ⅶ).

    응집도를 함께 본다 — 기관이 많아도 서로 무관한 문서 더미면 약한 신호다.
    """
    o, d, co = len(c.orgs), len(c.docs), c.cohesion
    if (o >= 5 and co >= 3) or co >= 6:
        return 5
    if (o >= 4 and co >= 2) or co >= 4:
        return 4
    if o >= 3 or co >= 2:
        return 3
    if o >= 2 or d >= 3:
        return 2
    return 1


def representative_title(c: Cluster) -> str:
    """클러스터를 대표할 문서 제목을 고른다.

    제목을 지어내지 않는다. 공유어를 가장 많이 담은 실제 문서를 그대로 쓴다.
    (운영 단계에서 AI가 이 자리를 더 나은 문장으로 바꾼다.)
    """
    shared = set(c.cohesion_keywords)
    if not shared:
        return min(c.docs, key=lambda d: len(d["title"]))["title"]
    return max(
        c.docs,
        key=lambda d: (len(shared & set(d["keywords"])), -len(d["title"])),
    )["title"]


def to_rows(clusters: list[Cluster], dates: list[str], limit: int) -> list[dict]:
    """클러스터를 signals 행으로. title/summary 는 임시 문구다 —
    운영 단계에서 AI가 채운다."""
    import json
    from datetime import datetime

    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for c in clusters[:limit]:
        ds = sorted(c.dates)
        shared = c.cohesion_keywords[:8]
        span = (f"{ds[0][4:6]}/{ds[0][6:]}"
                + (f"~{ds[-1][4:6]}/{ds[-1][6:]}" if ds[0] != ds[-1] else ""))
        rows.append({
            "signal_id": f"{ds[0]}_{c.keyword}",
            "keyword": c.keyword,
            "shared_terms": "\n".join(shared),
            "cohesion": c.cohesion,
            "title": representative_title(c),
            "summary": (
                f"{span}, {len(c.orgs)}개 기관에서 「{c.keyword}」 관련 문서 "
                f"{len(c.docs)}건이 생산됐다."
                + (f" 공통 키워드: {' · '.join(shared[:4])}." if shared else "")
            ),
            "signal_type": "동시다발",
            "strength": strength_of(c),
            "doc_count": len(c.docs),
            "org_count": len(c.orgs),
            "orgs": "\n".join(sorted(c.orgs)),
            # doc_key + produced_at 이 있어야 원문 상세로 직접 링크할 수 있다.
            # 기획서 Ⅴ "근거 문서 원문 링크"는 타협 불가 항목이다.
            "source_docs": json.dumps(
                [{"date": d["date"], "org": d["org"], "dept": d["dept"],
                  "title": d["title"], "doc_key": d.get("doc_key", ""),
                  "produced_at": d.get("produced_at", "")} for d in c.docs],
                ensure_ascii=False),
            "period_from": ds[0],
            "period_to": ds[-1],
            "detected_at": now,
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="통계 기반 신호 탐지")
    p.add_argument("--db", default="data/signals.db")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--min-orgs", type=int, default=2, help="최소 기관 수")
    p.add_argument("--min-docs", type=int, default=2, help="최소 문서 수")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--df-cut", type=float, default=0.02,
                   help="전건 기준 가장 흔한 상위 비율의 키워드를 제외 (기본 2%%)")
    p.add_argument("--save", action="store_true",
                   help="signals 테이블에 저장 (웹사이트가 읽는다)")
    p.add_argument("--save-limit", type=int, default=40)
    args = p.parse_args(argv)

    with Store(args.db) as store:
        dates = [r["date"] for r in store.conn.execute(
            "SELECT DISTINCT date FROM docs ORDER BY date DESC LIMIT ?", (args.days,)
        )][::-1]
        if not dates:
            print("수집된 데이터가 없다. collector.run 을 먼저 돌려라.")
            return 1

        docs = load_docs(store, dates)
        idf = build_idf(store, dates)
        print(f"기간 {dates[0]}~{dates[-1]} ({len(dates)}일) · "
              f"통과 문서 {len(docs):,}건 · 키워드 사전 {len(idf):,}종")

        banned = common_keywords(idf, args.df_cut)
        print(f"  흔한 키워드 {len(banned):,}종 제외 (상위 {args.df_cut:.0%})")
        clusters = build_clusters(docs, idf, args.min_orgs, args.min_docs, banned)
        spikes = find_spikes(store, dates)
        report(clusters, spikes, args.top)

        if args.save:
            rows = to_rows(clusters, dates, args.save_limit)
            store.save_signals(rows)
            store.conn.commit()
            print(f"\n✅ signals 테이블에 {len(rows)}건 저장 "
                  f"(published=0 — 검수 후 공개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
