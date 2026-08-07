"""AI 해석 — 통계로 뽑은 클러스터에 이름과 맥락을 붙인다.

    set GEMINI_API_KEY=...
    python -m collector.summarize            # 아직 해석 안 된 신호만
    python -m collector.summarize --all      # 전부 다시
    python -m collector.summarize --dry-run  # 프롬프트만 보고 호출은 안 함

설계 원칙 (기획서 §Ⅲ-3-2, §Ⅵ)
------------------------------
1. **AI에게 추측시키지 않는다.** 통계가 이미 "몇 개 기관이 며칠에 걸쳐 무엇을
   공유하는가"를 확정했다. AI는 그 묶음에 이름을 붙이고 맥락을 설명할 뿐이다.
2. **문서 제목 밖의 사실을 지어내지 못하게 한다.** 제목에 없는 배경·수치·
   전망을 쓰지 말라고 명시하고, 모르면 모른다고 하게 한다.
3. **묶어서 호출한다.** 무료 등급은 일일 요청 수가 제한된다. 신호 하나당
   1요청이면 한도를 넘긴다. 여러 건을 한 요청에 넣는다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

from .db import Store

# `gemini-flash-latest` 는 최신 flash 를 따라가는 별칭이다.
# 버전을 고정하면 언젠가 "이 모델은 신규 사용자에게 제공되지 않는다"는 404를 맞는다
# (실측: gemini-2.5-flash 로 시작했다가 바로 겪었다).
# 재현성이 필요하면 `python -m collector.models` 로 확인 후 GEMINI_MODEL 로 고정한다.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

# 기획서 §ⅩⅡ-1 — 자유 서술로 두면 표에서 세어지지 않는다.
CATEGORIES = [
    "공급망", "산업지원", "규제", "예산재정",
    "인력고용", "지역", "대외협력", "기타",
]

SYSTEM = f"""당신은 정부 행정문서 흐름을 관측해 정책 신호를 정리하는 분석가입니다.

입력으로 '신호 묶음'들이 주어집니다. 각 묶음은 이미 통계로 확정된 사실입니다:
여러 중앙행정기관이 같은 기간에 같은 키워드를 공유하는 문서를 생산했다는 것.

당신의 일은 각 묶음에 **이름을 붙이고 맥락을 설명하는 것**입니다.

반드시 지킬 것:
- 주어진 문서 제목에 없는 사실을 만들어내지 마십시오. 배경 설명, 통계, 전망,
  정책 효과를 지어내면 안 됩니다.
- "정부가 ~를 추진 중이다" 처럼 단정하지 마십시오. 문서 제목에서 읽히는
  범위까지만 쓰십시오. 확실하지 않으면 "~로 보인다", "~단계로 읽힌다"를 쓰십시오.
- 여러 문서가 사실은 무관해 보이면 그렇게 쓰십시오. 억지로 하나의 이야기로
  묶지 마십시오.
- 문서가 일상적 행정 처리로만 보이면 summary에 그 사실을 명시하십시오.

각 묶음마다 다음을 씁니다:
- title: 무슨 일이 벌어지고 있는지 한 줄. 25자 내외. 문서 제목 복사 금지.
- summary: 2~3문장. 어느 부처가 무엇을 하고 있는지, 어느 단계로 보이는지.
- impact: 이 사안이 영향을 줄 대상. 한 줄. 불명확하면 "불명확".
- category: 다음 중 하나만 — {', '.join(CATEGORIES)}
- routine: 기관마다 주기적으로 하는 정형 행정업무면 true.
  (예: 정기 평가, 내부 교육, 성과관리, 정례 간담회, 서식 제출, 감사 대응)
  새로운 제도·법령·사업이 움직이는 것으로 보이면 false.
- notability: 정책 관측자에게 얼마나 알릴 가치가 있는지 1~5 정수.
  5 = 새 법령/제도가 실제로 움직임    4 = 새 사업·대책이 구체화
  3 = 기존 정책의 의미 있는 변화       2 = 통상적 행정, 맥락상 참고만
  1 = 알릴 가치 없음
  **routine 이 true 면 notability 는 2 이하여야 한다.**
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "impact": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "routine": {"type": "boolean"},
                    "notability": {"type": "integer"},
                },
                "required": ["id", "title", "summary", "impact", "category",
                             "routine", "notability"],
            },
        }
    },
    "required": ["results"],
}


def build_prompt(rows: list[dict]) -> str:
    parts = []
    for i, r in enumerate(rows, 1):
        docs = json.loads(r["source_docs"] or "[]")
        lines = [f"- [{d['org']}] {d['title']}" for d in docs[:12]]
        if len(docs) > 12:
            lines.append(f"- (외 {len(docs) - 12}건)")
        parts.append(
            f"### 묶음 {i}\n"
            f"id: {r['signal_id']}\n"
            f"공통 키워드: {r['keyword']}"
            + (f", {r['shared_terms'].replace(chr(10), ', ')}"
               if r["shared_terms"] else "")
            + f"\n관측: {r['org_count']}개 기관 · 문서 {r['doc_count']}건 · "
            f"{r['period_from']}~{r['period_to']}\n"
            f"문서 제목:\n" + "\n".join(lines)
        )
    return SYSTEM + "\n\n" + "\n\n".join(parts)


def call_gemini(prompt: str, api_key: str, schema: dict | None = None):
    """구조화 출력으로 호출한다. schema 를 주면 그 모양으로 받는다.

    프롬프트로 'JSON 으로 답해줘'라고 부탁만 하면 형식이 깨진다.
    responseSchema 로 강제해야 파싱이 안정된다.
    """
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema or SCHEMA,
            "temperature": 0.2,
        },
    }).encode()

    req = urllib.request.Request(
        ENDPOINT.format(model=MODEL),
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Gemini 호출 실패 {e.code}: {detail}") from None

    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(text)
    return parsed if schema else parsed.get("results", [])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="신호에 AI 해석 붙이기")
    p.add_argument("--db", default="data/signals.db")
    p.add_argument("--all", action="store_true", help="이미 해석된 것도 다시")
    p.add_argument("--batch", type=int, default=15,
                   help="한 요청에 넣을 신호 수")
    p.add_argument("--limit", type=int, default=60)
    p.add_argument("--dry-run", action="store_true",
                   help="프롬프트만 출력하고 호출하지 않는다")
    args = p.parse_args(argv)

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key and not args.dry_run:
        print("GEMINI_API_KEY 가 없다.\n"
              "  PowerShell:  $env:GEMINI_API_KEY = 'AIza...'\n"
              "  키 발급:      https://aistudio.google.com/apikey\n"
              "  (--dry-run 으로 프롬프트만 확인할 수 있다)")
        return 1

    with Store(args.db) as store:
        where = "" if args.all else "WHERE ai_generated_at = ''"
        rows = [dict(r) for r in store.conn.execute(
            f"SELECT * FROM signals {where} "
            f"ORDER BY cohesion DESC, org_count DESC LIMIT ?", (args.limit,)
        )]
        if not rows:
            print("해석할 신호가 없다. (--all 로 전체 재생성)")
            return 0

        print(f"대상 {len(rows)}건 · 배치 {args.batch}건씩 "
              f"→ 예상 {-(-len(rows) // args.batch)}요청")

        if args.dry_run:
            print("\n" + "=" * 70)
            print(build_prompt(rows[:args.batch])[:3000])
            print("=" * 70)
            return 0

        now = dt.datetime.now().isoformat(timespec="seconds")
        done = 0
        for i in range(0, len(rows), args.batch):
            chunk = rows[i:i + args.batch]
            print(f"  요청 {i // args.batch + 1} — {len(chunk)}건 …", end=" ")
            try:
                results = call_gemini(build_prompt(chunk), api_key)
            except Exception as e:
                print(f"실패: {e}")
                continue

            by_id = {r["id"]: r for r in results}
            for r in chunk:
                got = by_id.get(r["signal_id"])
                if not got:
                    continue
                # 1~5 정수로 강제한다. 범위를 벗어나면 저장이 무의미해진다.
                note = max(1, min(5, int(got.get("notability", 3) or 3)))
                store.conn.execute(
                    "UPDATE signals SET ai_title=?, ai_summary=?, ai_impact=?,"
                    " ai_category=?, ai_routine=?, ai_notability=?,"
                    " ai_model=?, ai_generated_at=? WHERE signal_id=?",
                    (got["title"], got["summary"], got["impact"],
                     got["category"], 1 if got.get("routine") else 0, note,
                     MODEL, now, r["signal_id"]),
                )
                done += 1
            store.conn.commit()
            print(f"완료 ({len(by_id)}건)")

        print(f"\n✅ {done}건에 AI 해석을 붙였다 (모델 {MODEL})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
