"""일일 배치 — 수집 → 신호 탐지 → 저장을 한 번에.

GitHub Actions 가 매일 새벽 이것만 부르면 된다.
웹사이트는 `signals` 테이블을 60초 캐시로 읽으므로 자동으로 반영된다.

    python -m collector.pipeline                 # 어제치
    python -m collector.pipeline --date 20260806
    python -m collector.pipeline --lookback 14   # 신호 탐지 기간
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from .browser_client import BrowserClient
from .client import INSTT_SE
from .db import Store
from .run import cmd_collect, ymd
from .signals import build_clusters, build_idf, find_spikes, load_docs, to_rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="일일 배치 (수집 + 신호 탐지)")
    p.add_argument("--date", help="수집 대상일 yyyymmdd (기본: 어제)")
    p.add_argument("--instt", default="중앙행정기관", choices=list(INSTT_SE))
    p.add_argument("--db", default="data/signals.db")
    p.add_argument("--lookback", type=int, default=14,
                   help="신호 탐지에 쓸 과거 일수")
    p.add_argument("--min-orgs", type=int, default=2)
    p.add_argument("--min-docs", type=int, default=2)
    p.add_argument("--save-limit", type=int, default=40)
    p.add_argument("--skip-collect", action="store_true",
                   help="수집 없이 신호 탐지만 다시 돌린다")
    args = p.parse_args(argv)

    date = args.date or ymd(dt.date.today() - dt.timedelta(days=1))
    instt_se = INSTT_SE[args.instt]

    with Store(args.db) as store:
        # 1) 수집
        if not args.skip_collect:
            print(f"■ 1/2 수집 — {date}")
            with BrowserClient() as client:
                cmd_collect(client, store, date, instt_se,
                            max_pages=None, force=False)

        # 2) 신호 탐지
        print(f"\n■ 2/2 신호 탐지 — 최근 {args.lookback}일")
        dates = [r["date"] for r in store.conn.execute(
            "SELECT DISTINCT date FROM docs ORDER BY date DESC LIMIT ?",
            (args.lookback,),
        )][::-1]
        if not dates:
            print("  수집된 문서가 없다.")
            return 1

        docs = load_docs(store, dates)
        idf = build_idf(store, dates)
        clusters = build_clusters(docs, idf, args.min_orgs, args.min_docs)
        spikes = find_spikes(store, dates)

        rows = to_rows(clusters, dates, args.save_limit)
        store.save_signals(rows)
        store.conn.commit()

        print(f"  기간 {dates[0]}~{dates[-1]} ({len(dates)}일) · "
              f"문서 {len(docs):,}건")
        print(f"  클러스터 {len(clusters):,}개 · 급증 {len(spikes):,}건")
        print(f"  ✅ signals {len(rows)}건 저장 (published=0 — 검수 후 공개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
