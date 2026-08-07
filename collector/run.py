"""배치 엔트리포인트.

    python -m collector.run --date 20260806
    python -m collector.run --date 20260806 --max-pages 5   # 맛보기
    python -m collector.run --count-only --days 7           # 건수만 측정 (S2)

수집 흐름 (기획서 Ⅱ-2)
    목록 페이징(전건) ──> 카운터 +1 ──> 버림
                      └─> 룰 필터 통과분만 ──> 저장
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter

from .browser_client import BrowserClient
from .client import INSTT_SE
from .db import Store
from .filters import FilterStats, apply


def ymd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def cmd_count(client: BrowserClient, days: int, instt_se: str) -> None:
    """S2 — 일별 건수만 측정한다. 하루당 1요청."""
    today = dt.date.today()
    print(f"[건수 측정] 기관구분={instt_se}  최근 {days}일\n")
    total = 0
    for i in range(1, days + 1):
        d = ymd(today - dt.timedelta(days=i))
        n = client.count(d, instt_se)
        total += n
        print(f"  {d}   {n:>9,}건")
    print(f"\n  평균 {total // days:,}건/일")
    print(f"  페이지 200건 기준 하루 약 {total // days // 200 + 1}요청 "
          f"(약 {(total // days // 200 + 1) * 1.5 / 60:.0f}분)")


def cmd_collect(
    client: BrowserClient, store: Store, date: str, instt_se: str,
    max_pages: int | None, force: bool,
) -> None:
    if store.already_done(date, instt_se) and not force:
        print(f"[건너뜀] {date}/{instt_se} 는 이미 수집됨 (--force 로 재수집)")
        return

    print(f"[수집] {date}  기관구분={instt_se}")
    total = client.count(date, instt_se)
    print(f"  대상 {total:,}건  ≈ {total // 200 + 1} 페이지")

    stats = FilterStats()
    org_counts: Counter[str] = Counter()
    kw_counts: Counter[tuple[str, str]] = Counter()
    batch: list = []
    saved = 0

    def flush() -> None:
        nonlocal saved, batch
        if batch:
            saved += store.save_docs(batch)
            store.conn.commit()
            batch = []

    stream = client.iter_day(date, instt_se, max_pages=max_pages)
    for doc in apply(_tap(stream, org_counts, kw_counts), stats):
        batch.append(doc)
        if len(batch) >= 500:
            flush()
            print(f"    ... 훑음 {stats.total:,} / 저장 {saved + len(batch):,}")
    flush()

    store.record_daily_total(date, instt_se, total)
    store.record_org_counts(date, instt_se, org_counts)
    store.record_keywords(date, kw_counts)
    store.record_run(
        date, instt_se, stats.total, saved, stats.drop_rate,
        dt.datetime.now().isoformat(timespec="seconds"),
    )
    store.conn.commit()

    print()
    print(stats.report())
    print(f"\n  저장 {saved:,}건 · 기관 {len(org_counts):,}개 · 키워드쌍 {len(kw_counts):,}개")
    if stats.drop_rate < 0.85:
        print(f"  ⚠️  제거율 {stats.drop_rate:.1%} — 목표 85% 미달. filters.py 보강 필요")


def _tap(stream, org_counts: Counter, kw_counts: Counter):
    """필터 이전에 전건을 세고 흘려보낸다. 저장은 하지 않는다."""
    for doc in stream:
        org_counts[doc.org] += 1
        for kw in doc.keywords:
            kw_counts[(kw, doc.org)] += 1
        yield doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="open.go.kr 정책 신호 수집기")
    p.add_argument("--date", help="수집 대상일 yyyymmdd (기본: 어제)")
    p.add_argument("--days-back", type=int,
                   help="어제부터 N일치를 한 번에 수집 (--date 무시)")
    p.add_argument("--instt", default="중앙행정기관", choices=list(INSTT_SE),
                   help="기관구분 (기본: 중앙행정기관)")
    p.add_argument("--max-pages", type=int, help="페이지 수 제한 (맛보기용)")
    p.add_argument("--count-only", action="store_true", help="건수만 측정")
    p.add_argument("--days", type=int, default=7, help="--count-only 시 측정 일수")
    p.add_argument("--db", default="data/signals.db")
    p.add_argument("--force", action="store_true", help="이미 수집한 날짜도 재수집")
    args = p.parse_args(argv)

    instt_se = INSTT_SE[args.instt]

    with BrowserClient() as client:
        if args.count_only:
            cmd_count(client, args.days, instt_se)
            return 0
        if args.days_back:
            dates = [ymd(dt.date.today() - dt.timedelta(days=i))
                     for i in range(1, args.days_back + 1)]
        else:
            dates = [args.date or ymd(dt.date.today() - dt.timedelta(days=1))]

        with Store(args.db) as store:
            for i, date in enumerate(dates, 1):
                print(f"\n{'='*60}\n[{i}/{len(dates)}] {date}\n{'='*60}")
                try:
                    cmd_collect(client, store, date, instt_se,
                                args.max_pages, args.force)
                except Exception as e:  # 하루 실패가 전체를 멈추지 않게
                    print(f"  ⚠️ {date} 실패: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
