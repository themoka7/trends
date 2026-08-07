"""현재 필터 기준으로 docs 테이블을 정리한다.

필터 규칙을 바꾼 뒤, 예전 규칙으로 저장된 문서를 걷어낼 때 쓴다.

    python -m collector.cleanup            # 미리보기
    python -m collector.cleanup --apply    # 실제 삭제
"""

from __future__ import annotations

import argparse
import sys

from .client import Doc
from .db import Store
from .filters import classify


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="현재 필터로 docs 재검증")
    p.add_argument("--db", default="data/signals.db")
    p.add_argument("--apply", action="store_true", help="실제로 삭제한다")
    args = p.parse_args(argv)

    with Store(args.db) as store:
        rows = store.conn.execute(
            "SELECT doc_key, title, org, dept, unit_job FROM docs"
        ).fetchall()

        stale = []
        for r in rows:
            doc = Doc(
                doc_key=r["doc_key"], title=r["title"], org=r["org"],
                dept=r["dept"], org_code="", unit_job=r["unit_job"] or "",
                theme="", doc_no="", open_type="", produced_at="",
                date="", keywords=(),
            )
            if not classify(doc)[0]:
                stale.append(r["doc_key"])

        print(f"전체 {len(rows):,}건 · 현재 필터 미통과 {len(stale):,}건")
        if not args.apply:
            print("(미리보기 — 실제로 지우려면 --apply)")
            return 0

        store.conn.executemany(
            "DELETE FROM docs WHERE doc_key=?", [(k,) for k in stale]
        )
        store.conn.commit()
        left = store.conn.execute("SELECT COUNT(*) c FROM docs").fetchone()["c"]
        print(f"삭제 완료 · 남은 문서 {left:,}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
