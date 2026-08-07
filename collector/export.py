"""웹사이트가 읽을 JSON을 만든다.

    python -m collector.export

왜 JSON인가
-----------
GitHub Pages 는 정적 호스팅이라 서버에서 DB를 읽을 수 없다.
배치가 결과를 JSON으로 떨구고 사이트는 빌드 시점에 그걸 읽는다.
서버도 외부 DB도 필요 없어 **전부 무료**로 돌아간다.

나중에 실시간성이 필요해지면 Turso 로 옮기고 이 파일을 지우면 된다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .db import Store

DEFAULT_OUT = "web/public/feed.json"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="웹사이트용 JSON 내보내기")
    p.add_argument("--db", default="data/signals.db")
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--limit", type=int, default=80)
    p.add_argument("--include-unpublished", action="store_true", default=True,
                   help="파일럿 단계에서는 미검수분도 내보낸다")
    p.add_argument("--allow-empty", action="store_true",
                   help="사안이 0건이어도 기존 feed 를 덮어쓴다")
    args = p.parse_args(argv)

    with Store(args.db) as store:
        where = "" if args.include_unpublished else "WHERE published = 1"
        signals = []
        for r in store.conn.execute(
            f"SELECT * FROM signals {where} "
            f"ORDER BY ai_notability DESC, cohesion DESC, org_count DESC LIMIT ?",
            (args.limit,),
        ):
            d = dict(r)
            signals.append({
                "id": d["signal_id"],
                "keyword": d["keyword"],
                "sharedTerms": [t for t in (d["shared_terms"] or "").split("\n") if t],
                "cohesion": d["cohesion"],
                "title": d["title"],
                "summary": d["summary"],
                "strength": d["strength"],
                "docCount": d["doc_count"],
                "orgCount": d["org_count"],
                "orgs": [o for o in (d["orgs"] or "").split("\n") if o],
                "sourceDocs": json.loads(d["source_docs"] or "[]"),
                "periodFrom": d["period_from"],
                "periodTo": d["period_to"],
                "published": bool(d["published"]),
                "ai": {
                    "title": d["ai_title"],
                    "summary": d["ai_summary"],
                    "impact": d["ai_impact"],
                    "category": d["ai_category"],
                    "routine": bool(d["ai_routine"]),
                    "notability": d["ai_notability"],
                    "model": d["ai_model"],
                    "generatedAt": d["ai_generated_at"],
                } if d["ai_generated_at"] else None,
            })

        b = store.conn.execute(
            "SELECT * FROM briefings ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
        brief = None
        if b:
            brief = {
                "headline": b["headline"],
                "overview": b["overview"],
                "byCategory": json.loads(b["by_category"] or "[]"),
                "watch": json.loads(b["watch"] or "[]"),
                "periodFrom": b["period_from"],
                "periodTo": b["period_to"],
                "model": b["model"],
                "generatedAt": b["generated_at"],
            }

        s = store.conn.execute(
            "SELECT COUNT(*) days, SUM(scanned) scanned, SUM(kept) kept,"
            " MIN(date) f, MAX(date) t FROM runs"
        ).fetchone()
        # 일자별 추이 — 화면에서 수집 리듬을 보여준다.
        # 주말이 확 꺼지는 모양이 그 자체로 정보가 된다.
        daily = [
            {"date": d["date"], "scanned": d["scanned"], "kept": d["kept"]}
            for d in store.conn.execute(
                "SELECT date, scanned, kept FROM runs ORDER BY date"
            )
        ]

        stats = {
            "days": s["days"] or 0,
            "scanned": s["scanned"] or 0,
            "kept": s["kept"] or 0,
            "from": s["f"] or "",
            "to": s["t"] or "",
            "daily": daily,
        }

    out = Path(args.out)

    # ⚠️ 빈 결과로 기존 feed 를 덮어쓰지 않는다.
    #    CI에서 DB 캐시가 비었을 때 export 가 돌아 좋은 feed.json 을
    #    0건짜리로 덮어쓴 적이 있다. 사이트가 통째로 비어 보였다.
    if not signals and out.exists():
        print(f"⚠️ 사안 0건 — 기존 {out} 를 지키고 종료한다. "
              f"(강제로 쓰려면 --allow-empty)")
        if not args.allow_empty:
            return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"brief": brief, "stats": stats, "signals": signals},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    size = out.stat().st_size / 1024
    print(f"✅ {out} · 사안 {len(signals)}건 · {size:.0f}KB"
          + (" · 리포트 포함" if brief else " · 리포트 없음"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
