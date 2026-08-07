"""open.go.kr 정보목록 API 클라이언트.

브라우저 자동화 없이 목록 AJAX 엔드포인트를 직접 호출한다.
    POST /othicInfo/infoList/infoList.ajax  ->  JSON

⚠️ 응답에는 담당자 실명(CHARGER_NM)이 포함된다.
   normalize() 에서 절대 담지 않는다. 이 파일 밖으로 실명이 나가지 않게 한다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterator

import requests

BASE = "https://www.open.go.kr"
LIST_ENDPOINT = f"{BASE}/othicInfo/infoList/infoList.ajax"

# 기관구분 코드 (사이트 체크박스 value)
INSTT_SE = {
    "중앙행정기관": "C",
    "광역자치단체": "W",
    "기초자치단체": "B",
    "교육청": "E",
    "공공기관": "P",
}

# 공개구분 코드
OTHBC_SE = {"1": "공개", "2": "부분공개", "3": "비공개"}

# 페이지당 최대 건수. 200까지 동작하는 것을 실측 확인했다.
ROWS_PER_PAGE = 200

# 요청 간격(초).
#
# ⚠️ 1.5초로 191페이지를 연속 요청했더니 `code: 429` 로 막혔다.
#    소량(14페이지)에서 괜찮았다고 대량에서도 괜찮은 게 아니다.
#    줄이지 말 것 — 차단되면 서비스가 통째로 멈춘다.
REQUEST_INTERVAL = 3.0

# 429를 맞았을 때 물러섰다 다시 시도하는 간격(초). 지수적으로 늘린다.
BACKOFF_BASE = 20.0
BACKOFF_MAX_RETRIES = 4

# HTTP 헤더는 latin-1만 허용된다. 한글을 넣으면 UnicodeEncodeError.
USER_AGENT = (
    "PolicySignalBot/0.1 (policy trend feed collector; "
    "contact: jm3280@pusan.ac.kr) python-requests"
)


@dataclass(frozen=True)
class Doc:
    """정규화된 문서 1건. 담당자 실명은 담지 않는다."""

    doc_key: str  # PRDCTN_INSTT_REGIST_NO — 문서 고유 ID
    title: str
    org: str  # 기관명
    dept: str  # 담당부서명
    org_code: str
    unit_job: str  # 단위업무 (중앙행정기관은 채워져 있다)
    theme: str  # 사이트 자체 주제분류 — 참고용, 신뢰도 낮음
    doc_no: str
    open_type: str  # 공개/부분공개/비공개
    produced_at: str  # PRDCTN_DT (yyyymmddHHMMSS)
    date: str  # yyyymmdd
    keywords: tuple[str, ...]  # tma_kwd — 사이트가 이미 추출해 준 키워드


def normalize(raw: dict) -> Doc:
    """API 응답 1행을 Doc으로 변환한다.

    CHARGER_NM(담당자 실명)은 의도적으로 읽지 않는다.
    """
    kw = tuple(k for k in (raw.get("tma_kwd") or "").split("\n") if k.strip())
    return Doc(
        doc_key=raw.get("PRDCTN_INSTT_REGIST_NO", ""),
        title=(raw.get("INFO_SJ") or "").strip(),
        org=(raw.get("PROC_INSTT_NM") or "").strip(),
        dept=(raw.get("CHRG_DEPT_NM") or "").strip(),
        org_code=(raw.get("INSTT_CD") or "").strip(),
        unit_job=(raw.get("UNIT_JOB_NM") or "").strip(),
        theme=(raw.get("RQEST_TY_THEMA_NM") or "").strip(),
        doc_no=(raw.get("DOC_NO") or "").strip(),
        open_type=OTHBC_SE.get(raw.get("OTHBC_SE_CD", ""), ""),
        produced_at=(raw.get("PRDCTN_DT") or "").strip(),
        date=(raw.get("P_DATE") or "").strip(),
        keywords=kw,
    )


class OpenGoClient:
    def __init__(self, interval: float = REQUEST_INTERVAL):
        self.interval = interval
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": f"{BASE}/othicInfo/infoList/infoList.do",
            }
        )
        self._last_call = 0.0
        self._warmed = False

    def _warmup(self) -> None:
        """목록 페이지를 먼저 GET 해서 세션 쿠키를 받는다.

        이 사이트는 AJAX만 단독으로 부르면 HTTP 200에 0건을 돌려준다.
        세션이 있어야 조회가 성립한다.
        """
        if self._warmed:
            return
        self._throttle()
        r = self.session.get(
            f"{BASE}/othicInfo/infoList/infoList.do",
            headers={"Accept": "text/html"},
            timeout=30,
        )
        r.raise_for_status()
        self._warmed = True

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last_call = time.monotonic()

    def fetch_page(
        self, date: str, instt_se: str = "C", page: int = 1, rows: int = ROWS_PER_PAGE
    ) -> tuple[list[Doc], int]:
        """하루치 목록 한 페이지. (문서 목록, 전체 건수) 반환."""
        self._warmup()
        self._throttle()
        body = {
            "category": "info",
            "eduYn": "N",
            "startDate": date,
            "endDate": date,
            "insttSeCd": instt_se,
            "kwd": "",
            "insttCd": "",
            "othbcSeCd": "",
            "rowPage": str(rows),
            "viewPage": str(page),
            "sort": "s",
        }
        resp = self.session.post(LIST_ENDPOINT, data=body, timeout=30)
        resp.raise_for_status()
        result = resp.json().get("result") or {}
        docs = [normalize(r) for r in (result.get("rtnList") or [])]
        return docs, int(result.get("rtnTotal") or 0)

    def count(self, date: str, instt_se: str = "C") -> int:
        """건수만 센다. 1요청."""
        _, total = self.fetch_page(date, instt_se, page=1, rows=10)
        return total

    def iter_day(
        self, date: str, instt_se: str = "C", max_pages: int | None = None
    ) -> Iterator[Doc]:
        """하루치를 페이지 단위로 순회한다.

        중복 doc_key는 건너뛴다 (페이지 경계에서 겹칠 수 있다).
        """
        seen: set[str] = set()
        page = 1
        total = None
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
            if len(seen) >= total:
                break
            page += 1
            if max_pages and page > max_pages:
                break
