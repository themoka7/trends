"""이 API 키로 쓸 수 있는 Gemini 모델 목록.

    python -m collector.models

모델 이름은 자주 바뀌고 신규 사용자에게는 구형 모델이 막힌다.
추측하지 말고 이걸로 확인한 뒤 GEMINI_MODEL 에 넣는다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

URL = "https://generativelanguage.googleapis.com/v1beta/models"


def main() -> int:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("GEMINI_API_KEY 가 없다.")
        return 1

    req = urllib.request.Request(URL, headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"조회 실패 {e.code}: {e.read().decode(errors='replace')[:400]}")
        return 1

    models = [
        m for m in data.get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    print(f"generateContent 가능한 모델 {len(models)}개\n")
    for m in sorted(models, key=lambda x: x["name"]):
        name = m["name"].removeprefix("models/")
        inp = m.get("inputTokenLimit", "?")
        out = m.get("outputTokenLimit", "?")
        print(f"  {name:<44} in {inp:>9} / out {out:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
