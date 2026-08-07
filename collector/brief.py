"""1장짜리 종합 리포트 — 기간 전체를 AI가 총평한다.

    python -m collector.brief
    python -m collector.brief --dry-run

개별 사안 요약(summarize.py)과 다르다. 저쪽은 사안 하나하나에 이름을 붙이고,
이쪽은 **그 전부를 놓고 "이 기간 정부는 무엇을 하고 있었나"** 를 쓴다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

from .db import Store
from .summarize import MODEL, call_gemini

SYSTEM = """당신은 정부 행정문서 흐름을 분석해 1장짜리 리포트를 쓰는 분석가입니다.

아래는 일정 기간 여러 중앙행정기관이 생산한 문서를 통계로 묶은 '사안' 목록입니다.
각 사안에는 이미 개별 요약이 붙어 있습니다.

당신의 일은 **이 전부를 놓고 기간 전체를 총평하는 것**입니다.

반드시 지킬 것:
- 주어진 사안 목록에 없는 사실을 만들어내지 마십시오.
- 정부의 의도나 배후를 추측하지 마십시오. 관측된 것만 쓰십시오.
- 일상적 행정업무가 대부분이면 그렇게 쓰십시오. 억지로 큰 흐름을 만들지 마십시오.
- 숫자를 지어내지 마십시오. 주어진 건수만 쓰십시오.

다음을 씁니다:
- headline: 이 기간을 한 줄로. 30자 내외.
- overview: 3~5문장 총평. 무엇이 두드러졌고 무엇이 일상적이었는지.
- by_category: 분야별 한 줄 평. 사안이 있는 분야만.
- watch: 눈여겨볼 사안 id 3~6개. notability 가 높고 정책적으로 의미 있는 것 위주.
  일상 업무(routine)는 넣지 마십시오.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "overview": {"type": "string"},
        "by_category": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["category", "note"],
            },
        },
        "watch": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "overview", "by_category", "watch"],
}


def build_prompt(rows: list[dict], stats: dict) -> str:
    lines = [
        f"기간: {stats['from']} ~ {stats['to']}",
        f"수집: 전체 문서 {stats['scanned']:,}건 중 {stats['kept']:,}건 분석",
        f"사안: {len(rows)}개",
        "",
        "## 사안 목록",
    ]
    for r in rows:
        lines.append(
            f"- id={r['signal_id']} | [{r['ai_category'] or '미분류'}] "
            f"{r['ai_title'] or r['title']}\n"
            f"  기관 {r['org_count']}개 · 문서 {r['doc_count']}건"
            f" · 주목도 {r['ai_notability']}"
            f"{' · 일상업무' if r['ai_routine'] else ''}\n"
            f"  {r['ai_summary'] or ''}"
        )
    return SYSTEM + "\n\n" + "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="1장짜리 종합 리포트 생성")
    p.add_argument("--db", default="data/signals.db")
    p.add_argument("--limit", type=int, default=60)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key and not args.dry_run:
        print("GEMINI_API_KEY 가 없다. https://aistudio.google.com/apikey")
        return 1

    with Store(args.db) as store:
        rows = [dict(r) for r in store.conn.execute(
            "SELECT * FROM signals WHERE ai_generated_at <> '' "
            "ORDER BY ai_notability DESC, cohesion DESC LIMIT ?", (args.limit,)
        )]
        if not rows:
            print("AI 해석된 사안이 없다. collector.summarize 를 먼저 돌려라.")
            return 1

        r = store.conn.execute(
            "SELECT MIN(date) f, MAX(date) t, SUM(scanned) s, SUM(kept) k FROM runs"
        ).fetchone()
        stats = {"from": r["f"] or "", "to": r["t"] or "",
                 "scanned": r["s"] or 0, "kept": r["k"] or 0}

        prompt = build_prompt(rows, stats)
        if args.dry_run:
            print(prompt[:3500])
            return 0

        print(f"사안 {len(rows)}개로 종합 리포트 생성 …")
        out = call_gemini(prompt, api_key, schema=SCHEMA)

        now = dt.datetime.now().isoformat(timespec="seconds")
        store.conn.execute(
            "INSERT OR REPLACE INTO briefings(brief_id, period_from, period_to,"
            " headline, overview, by_category, watch, doc_total, signal_total,"
            " model, generated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"{stats['from']}_{stats['to']}", stats["from"], stats["to"],
             out.get("headline", ""), out.get("overview", ""),
             json.dumps(out.get("by_category", []), ensure_ascii=False),
             json.dumps(out.get("watch", []), ensure_ascii=False),
             stats["kept"], len(rows), MODEL, now),
        )
        store.conn.commit()
        print(f"✅ 리포트 생성 — {out.get('headline', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
