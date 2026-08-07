"""브라우저 컨텍스트 기반 수집 클라이언트.

왜 Playwright인가
-----------------
목록 AJAX(`infoList.ajax`)를 순수 HTTP(requests / curl_cffi + Chrome TLS)로 부르면
HTTP 200 에 `code: 491` 만 돌아오고 데이터가 비어 있다. 실측으로 배제한 가설:

  · 세션 쿠키 부재        → warmup GET 후에도 491
  · XSRF-TOKEN 헤더 누락  → 토큰을 붙여도 491
  · TLS 핑거프린팅        → curl_cffi(impersonate=chrome) 로도 491
  · 검색조건 세션 미등록  → .do GET/POST 선행 3가지 시나리오 모두 491

반면 **실제 브라우저 페이지 컨텍스트에서 같은 fetch를 하면 정상 응답**한다.
사이트가 WAF(elevisor)를 쓰고 있어 JS 실행 컨텍스트를 요구하는 것으로 보인다.

따라서 페이지를 한 번 열고, 그 안에서 fetch 루프를 돌린다.
페이지는 1회만 열고 재사용하므로 오버헤드는 최초 1회뿐이다.
"""

from __future__ import annotations

import time
from typing import Iterator

from playwright.sync_api import sync_playwright

from .client import (
    BACKOFF_BASE,
    BACKOFF_MAX_RETRIES,
    BASE,
    INSTT_SE,
    REQUEST_INTERVAL,
    ROWS_PER_PAGE,
    Doc,
    normalize,
)

LIST_URL = f"{BASE}/othicInfo/infoList/infoList.do"

# 페이지 안에서 실행할 fetch. 브라우저 컨텍스트라 WAF를 통과한다.
_FETCH_JS = """
async ({date, insttSe, page, rows}) => {
  const body = new URLSearchParams({
    category: 'info', eduYn: 'N',
    startDate: date, endDate: date,
    insttSeCd: insttSe,
    kwd: '', insttCd: '', othbcSeCd: '',
    rowPage: String(rows), viewPage: String(page), sort: 's'
  });
  const r = await fetch('/othicInfo/infoList/infoList.ajax', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      'X-Requested-With': 'XMLHttpRequest'
    },
    body
  });
  const j = await r.json();
  const res = j.result || {};
  return { code: j.code, total: res.rtnTotal ?? null, rows: res.rtnList || [] };
}
"""


class BrowserClient:
    """`OpenGoClient` 와 같은 인터페이스. with 문으로 쓴다."""

    def __init__(self, interval: float = REQUEST_INTERVAL, headless: bool = True):
        self.interval = interval
        self.headless = headless
        self._last_call = 0.0
        self._pw = None
        self._browser = None
        self._page = None

    # -- 수명주기 -------------------------------------------------------------
    def __enter__(self) -> "BrowserClient":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        ctx = self._browser.new_context(
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        self._page = ctx.new_page()
        self._page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60_000)
        # 페이지 JS가 초기화되며 세션이 확립될 시간을 준다
        self._page.wait_for_timeout(2500)
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    # -- 내부 ----------------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last_call = time.monotonic()

    def _call(self, date: str, instt_se: str, page: int, rows: int) -> dict:
        self._throttle()
        return self._page.evaluate(
            _FETCH_JS,
            {"date": date, "insttSe": instt_se, "page": page, "rows": rows},
        )

    # -- 공개 API -------------------------------------------------------------
    def fetch_page(
        self, date: str, instt_se: str = "C", page: int = 1, rows: int = ROWS_PER_PAGE
    ) -> tuple[list[Doc], int]:
        """429(rate limit)를 만나면 물러섰다가 다시 시도한다.

        실측: 1.5초 간격으로 191페이지를 연속 요청하면 429가 뜬다.
        간격을 늘려도 장시간 수집에서는 결국 만나므로 백오프가 필요하다.
        """
        for attempt in range(BACKOFF_MAX_RETRIES + 1):
            r = self._call(date, instt_se, page, rows)
            code = r.get("code")

            if code in (None, 200, "200"):
                return [normalize(x) for x in r["rows"]], int(r.get("total") or 0)

            if str(code) == "429" and attempt < BACKOFF_MAX_RETRIES:
                wait = BACKOFF_BASE * (2 ** attempt)
                print(f"      · 429 — {wait:.0f}초 쉬었다 재시도 "
                      f"({attempt + 1}/{BACKOFF_MAX_RETRIES})")
                time.sleep(wait)
                # 세션을 새로 잡아 준다. 쿼터가 세션 단위일 수 있다.
                self._reload()
                continue

            raise RuntimeError(
                f"목록 조회 거부 (code={code}, page={page}). "
                "WAF에 막혔거나 세션이 만료됐다."
            )
        raise RuntimeError(f"429가 계속됨 (page={page}). 수집을 중단한다.")

    def _reload(self) -> None:
        """페이지를 다시 열어 세션을 갱신한다."""
        try:
            self._page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60_000)
            self._page.wait_for_timeout(2500)
        except Exception:
            pass

    def count(self, date: str, instt_se: str = "C") -> int:
        _, total = self.fetch_page(date, instt_se, page=1, rows=10)
        return total

    def iter_day(
        self, date: str, instt_se: str = "C", max_pages: int | None = None
    ) -> Iterator[Doc]:
        seen: set[str] = set()
        page = 1
        total: int | None = None
        while True:
            docs, rtn_total = self.fetch_page(date, instt_se, page=page)
            if total is None:
                total = rtn_total
            if not docs:
                break
            for d in docs:
                if d.doc_key and d.doc_key not in seen:
                    seen.add(d.doc_key)
                    yield d
            if total and len(seen) >= total:
                break
            page += 1
            if max_pages and page > max_pages:
                break


__all__ = ["BrowserClient", "INSTT_SE"]
