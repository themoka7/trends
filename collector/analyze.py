"""S4 필터 튜닝용 분석 도구.

하루치 전체를 다 받지 않고 **페이지를 균등 간격으로 표집**해서
기관 · 단위업무 · 부서 분포를 본다. 필터 규칙은 이 분포를 보고 만든다.

    python -m collector.analyze --date 20260806 --pages 12
    python -m collector.analyze --date 20260806 --pages 12 --out sample.json

왜 균등 표집인가
----------------
목록은 기관순으로 정렬되어 나온다. 앞에서 N페이지만 읽으면 특정 부처만
잡히고(실측: 5페이지 = 전부 법무부) 필터를 그 기관에 과적합시키게 된다.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict

from .browser_client import BrowserClient
from .client import INSTT_SE, ROWS_PER_PAGE, Doc
from .filters import classify


def sample_pages(total: int, n: int) -> list[int]:
    """전체 페이지에서 균등 간격으로 n개 골라낸다."""
    last = max(1, -(-total // ROWS_PER_PAGE))  # ceil
    if n >= last:
        return list(range(1, last + 1))
    step = last / n
    return sorted({int(i * step) + 1 for i in range(n)})


def collect_sample(client: BrowserClient, date: str, instt_se: str, pages: int):
    total = client.count(date, instt_se)
    targets = sample_pages(total, pages)
    print(f"대상 {total:,}건 / 전체 {-(-total // ROWS_PER_PAGE)}페이지 "
          f"중 {len(targets)}페이지 표집: {targets}\n")
    docs: list[Doc] = []
    for p in targets:
        got, _ = client.fetch_page(date, instt_se, page=p)
        docs.extend(got)
        print(f"  p{p:<4} +{len(got)}")
    return docs, total


def report(docs: list[Doc]) -> None:
    n = len(docs)
    print(f"\n{'='*72}\n표본 {n:,}건\n{'='*72}")

    org = Counter(d.org for d in docs)
    print(f"\n[기관 분포]  총 {len(org)}개")
    for k, v in org.most_common(20):
        print(f"  {v:>5}  {v/n:>5.1%}  {k}")

    uj = Counter(d.unit_job or "(비어있음)" for d in docs)
    samples: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        key = d.unit_job or "(비어있음)"
        if len(samples[key]) < 2:
            samples[key].append(d.title[:58])

    print(f"\n[단위업무 분포]  총 {len(uj)}종 — 상위 30")
    print(f"  {'건수':>5} {'비율':>6}  단위업무 / 제목 예시")
    cum = 0
    for k, v in uj.most_common(30):
        cum += v
        print(f"  {v:>5} {v/n:>6.1%}  {k[:44]}")
        for s in samples[k]:
            print(f"                 · {s}")
    print(f"  ── 상위 30종 누적 {cum:,}건 ({cum/n:.1%})")

    dept = Counter(d.dept for d in docs)
    print(f"\n[부서 분포]  총 {len(dept)}개 — 상위 20")
    for k, v in dept.most_common(20):
        print(f"  {v:>5}  {k}")

    # 현재 필터를 이 표본에 적용하면?
    kept = [d for d in docs if classify(d)[0]]
    print(f"\n[현재 필터 적용]  통과 {len(kept):,} / {n:,}  "
          f"(제거율 {1 - len(kept)/n:.1%})")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="필터 튜닝용 분포 분석")
    p.add_argument("--date")
    p.add_argument("--instt", default="중앙행정기관", choices=list(INSTT_SE))
    p.add_argument("--pages", type=int, default=12, help="표집할 페이지 수")
    p.add_argument("--out", help="표본을 JSON으로 저장할 경로")
    p.add_argument("--from-file", help="저장된 표본으로 오프라인 재분석 (네트워크 없음)")
    args = p.parse_args(argv)

    if args.from_file:
        with open(args.from_file, encoding="utf-8") as f:
            raw = json.load(f)
        docs = [
            Doc(doc_key="", title=r["title"], org=r["org"], dept=r["dept"],
                org_code="", unit_job=r["unit_job"], theme=r.get("theme", ""),
                doc_no="", open_type="", produced_at="", date="",
                keywords=tuple(r.get("keywords", [])))
            for r in raw
        ]
        report(docs)
        return 0

    if not args.date:
        p.error("--date 또는 --from-file 중 하나가 필요하다")

    with BrowserClient() as client:
        docs, total = collect_sample(client, args.date, INSTT_SE[args.instt], args.pages)

    report(docs)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(
                [{"title": d.title, "org": d.org, "dept": d.dept,
                  "unit_job": d.unit_job, "theme": d.theme,
                  "keywords": list(d.keywords)} for d in docs],
                f, ensure_ascii=False, indent=1,
            )
        print(f"\n표본 저장: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
