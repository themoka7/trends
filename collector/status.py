"""수집 현황 한눈에 보기.

    python -m collector.status

배치가 도는 중에도 읽을 수 있도록 읽기 전용으로 연다.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="수집 현황")
    p.add_argument("--db", default="data/signals.db")
    args = p.parse_args(argv)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    print("[일자별 수집]")
    rows = conn.execute(
        "SELECT date, scanned, kept, drop_rate FROM runs ORDER BY date"
    ).fetchall()
    if not rows:
        print("  (없음)")
    for r in rows:
        print(f"  {r['date']}   훑음 {r['scanned']:>7,}   "
              f"저장 {r['kept']:>5,}   제거율 {r['drop_rate']*100:>5.1f}%")

    def one(sql: str):
        return conn.execute(sql).fetchone()[0]

    print()
    print(f"  docs            {one('SELECT COUNT(*) FROM docs'):>8,}건")
    print(f"  기관            {one('SELECT COUNT(DISTINCT org) FROM docs'):>8,}개")
    print(f"  키워드 집계행    {one('SELECT COUNT(*) FROM keyword_daily'):>8,}행")
    print(f"  signals         {one('SELECT COUNT(*) FROM signals'):>8,}건")

    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM docs ORDER BY date")]
    print(f"  문서 보유 일자   {', '.join(dates) if dates else '(없음)'}")

    print("\n[기관별 통과 문서 상위 12]")
    for r in conn.execute(
        "SELECT org, COUNT(*) c FROM docs GROUP BY org ORDER BY c DESC LIMIT 12"
    ):
        print(f"  {r['c']:>5}  {r['org']}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
