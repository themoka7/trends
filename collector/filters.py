"""룰 필터 — AI에 태우기 전에 정책 신호가 될 만한 것만 남긴다.

목표 제거율 85% 이상 (기획서 S4).

왜 화이트리스트인가 (실측 근거)
--------------------------------
2026-08-06 중앙행정기관 2,800건 균등표집 결과:

  · 단위업무 **852종**, 부서 **832개** — 롱테일이 극심하다
  · 상위 부서: 운영지원과 · 보안과 · 보상과 · 총무과 · 복지과 …
    전부 일선 집행/서무 부서다
  · 상위 70종 단위업무를 다 걷어내도 누적 56%에 불과하다

즉 **블랙리스트로는 85%에 도달할 수 없다.** 중앙행정기관 문서의 대부분은
부처 본청의 정책 문서가 아니라 일선 기관(교도소·보훈지청·고용센터 등)의
개별 사건 처리 문서다.

그래서 **기본을 배제로 두고 통과 조건을 명시한다.**
놓치는 것이 생기지만, 그것은 S6 파일럿에서 판정할 문제다.
노이즈에 파묻혀 신호를 못 보는 쪽이 더 나쁘다.

판정 순서
---------
    1. 강한 배제 (명백한 정형 문서)        → 제외
    2. 통과 조건 (정책 부서 / 정책성 제목)  → 통과
    3. 그 외                               → 제외 (기본값)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .client import Doc

# ---------------------------------------------------------------------------
# 1. 강한 배제 — 통과 조건보다 먼저 본다.
#    "○○과 업무계획" 처럼 통과 패턴을 우연히 포함한 정형 문서를 걸러낸다.
# ---------------------------------------------------------------------------
HARD_DROP_TITLE: list[tuple[str, str]] = [
    ("일지대장", r"일지|대장|명령부|출근부|당직"),
    ("회계집행", r"지[출급]\s*(원인행위|결의|품의|요청)|집행\s*(내역|계획)\b|정산|급여|"
                 r"수당\s*지급|특근매식|초과근무|여비|세탁비|복지\s*포인트|"
                 r"관서운영경비|운영비|사례비|교부|반납\s*요청|보조금\s*(지급|교부)|"
                 r"수입\s*징수|징수\s*결의|기금\s*(수입|지출)"),
    ("공사설치", r"(설치|철거|교체|보수|개선)\s*(공사|작업)|전기\s*공사|"
                 r"공사\s*(계약|발주|감독|시행\s*계획)"),
    ("채용실무", r"(기간제|공무직|한시대체|계약직)\s*(근로자|직원)|채용\s*(공고|계획|시험)|"
                 r"참여연구원|위촉|해촉"),
    ("반송회신", r"^\s*\[반송\]|회원\s*가입|참석\s*(요청|협조)|알림\s*$"),
    ("인허가처리", r"신고\s*수리|변경\s*(신고|승인|허가|신청)|인가\s*(신청|처리)|"
                   r"적발|부정수급|과태료|이용\s*정지|처분\s*통보|수리\s*통보"),
    ("발급교부", r"발급\s*(신청|요청|안내)|증\s*발급|교부\s*신청|"
                 r"자료\s*(발급|제출)\s*요청|협조\s*요청\s*회신"),
    ("계약실무", r"수의시담|계약\s*(체결|변경|보증)\s*(안내|통보)|낙찰|입찰\s*공고|"
                 r"규격가격|계약방법\s*결정|검수|준공"),
    ("물품", r"물품\s*(구매|구입|청구|관리)|소모품|사무용품|비품"),
    ("개별민원", r"사실\s*조회|조회\s*(의뢰|요청)|의견\s*조회|회보\b|답변서|촉구|"
                 r"결정\s*통지서?|통지\s*\(|접수번호|공시송달|이의신청\s*처리|"
                 r"민원\s*[\(（]|처리\s*결과\s*안내|실적보고서"),
    ("개별사건", r"수용자|수형자|재소자|가석방|보호관찰\s*대상자|징벌|접견|영치|"
                 r"체류\s*(허가|자격)|출입국\s*내역|입건"),
    ("인사복무", r"현업공무원|호봉|재직\s*증명|복직|휴직|연가|병가|겸직|"
                 r"임용\s*예정자|결격사유|범죄경력"),
    ("등록신청처리", r"등록\s*(신청|처리|말소)|자격\s*(취득|상실)|수급자|"
                     r"신체검사|판정\s*(결과|통보)"),
    ("시설점검", r"작업\s*계획서|정기\s*점검|안전\s*점검\s*결과|검측|탐상|보수\s*공사|"
                 r"청사\s*(관리|보수)|냉난방|누수"),
    ("정보공개실무", r"정보공개\s*(청구|결정|처리)"),
]

# ---------------------------------------------------------------------------
# 2. 통과 조건 — 하나라도 걸리면 통과
# ---------------------------------------------------------------------------
KEEP_TITLE: list[tuple[str, str]] = [
    ("상급지시", r"\[지시\]|\[지시조사\]|지시\s*사항|긴급\s*(점검|대응)"),
    ("계획수립", r"(기본|종합|시행|추진|실행|사업)\s*계획|추진\s*\(?안\)?|"
                 r"로드맵|중장기|전략\s*수립"),
    ("제도변경", r"제도\s*개선|개선\s*(방안|대책)|종합\s*대책|"
                 r"(법률|법령|시행령|시행규칙|훈령|예규|고시|지침)\s*"
                 r"(제정|개정|폐지|안|입안)|규제\s*(개선|혁신|완화)"),
    ("예산편성", r"예산\s*(요구|편성|심의|안)|추가경정|재정\s*(계획|투자)"),
    ("정책연구", r"실태\s*조사|연구\s*용역|정책\s*연구|타당성\s*(조사|검토)|"
                 r"용역\s*(과업|발주|착수)"),
    ("사업추진", r"시범\s*(사업|운영)|공모\s*사업|육성|활성화\s*(방안|계획)|"
                 r"지원\s*(방안|대책|계획)"),
    ("대외협력", r"업무\s*협약|MOU|협의체|자문\s*(위원회|회의)|"
                 r"국제\s*(협력|협약)|관계부처"),
]

# 본청 정책 부서.
# ⚠️ 단독 통과 조건이 아니다. 실측 결과 정책부서 문서의 대다수도 정형 실무였다
#    (관서운영경비 지급결의 / 부속품 교체 구매 / 사업계획 변경 신고 수리 …).
#    아래 WEAK_POLICY 와 **함께** 걸릴 때만 통과시킨다.
KEEP_DEPT = re.compile(
    r"정책|기획(?!운영)|제도|총괄|혁신|전략|규제|미래|조정관|정책관"
)

# 약한 정책 어휘 — 단독으로는 부족하지만 정책부서와 만나면 신호가 된다
WEAK_POLICY = re.compile(
    r"방안|대책|검토\s*(의견|결과|보고)|의견\s*(제출|조회 없음)|개편|도입|"
    r"기준\s*(마련|개정)|가이드라인|매뉴얼|평가\s*(계획|결과)|"
    r"간담회|공청회|토론회|워크숍|연구회|협의\s*(회|결과)|"
    r"현황\s*(조사|분석)|동향|전망|과제|추진\s*상황|점검\s*계획"
)

# 단위업무 기준 강한 배제 (정규화 후 매칭)
HARD_DROP_UNIT: list[tuple[str, str]] = [
    ("단위_서무", r"서무|총무|청사|관사"),
    ("단위_민원", r"민원|상담|진정|고충|이의|심판|판정|감정"),
    ("단위_협조", r"업무\s*협조|자료\s*(제출|관리)|통계"),
    ("단위_회계", r"예산\s*및\s*회계|예산편성\s*및\s*집행|지출|회계|경리|급여"),
    ("단위_계약", r"계약|구매|조달|물품"),
    ("단위_인사", r"인사|복무|교육\s*훈련|채용|시험\s*관리"),
    ("단위_보안", r"보안|경비|방호|당직"),
    ("단위_개별처리", r"등록|신청|접수|허가|승인|지도\s*감독|사후\s*관리|"
                      r"수용|보호관찰|검역|단속"),
]

_HARD_DROP_TITLE = [(n, re.compile(p)) for n, p in HARD_DROP_TITLE]
_KEEP_TITLE = [(n, re.compile(p)) for n, p in KEEP_TITLE]
_HARD_DROP_UNIT = [(n, re.compile(p)) for n, p in HARD_DROP_UNIT]

# 단위업무 정규화: "서무업무(신규)", "(본청)서무업무" → "서무업무"
_UNIT_NOISE = re.compile(r"\((?:신규|본청|구|폐지)\)|\s+")


def norm_unit(s: str) -> str:
    return _UNIT_NOISE.sub("", s or "")


@dataclass
class FilterStats:
    total: int = 0
    kept: int = 0
    dropped: int = 0
    keep_hits: Counter = field(default_factory=Counter)
    drop_hits: Counter = field(default_factory=Counter)

    @property
    def drop_rate(self) -> float:
        return self.dropped / self.total if self.total else 0.0

    def report(self) -> str:
        lines = [
            f"전체 {self.total:,}건  →  통과 {self.kept:,}건  "
            f"제외 {self.dropped:,}건  (제거율 {self.drop_rate:.1%})",
            "", "[제외 사유]",
        ]
        for name, n in self.drop_hits.most_common():
            lines.append(f"  {name:<16} {n:>7,}")
        lines += ["", "[통과 사유]"]
        for name, n in self.keep_hits.most_common():
            lines.append(f"  {name:<16} {n:>7,}")
        return "\n".join(lines)


def classify(doc: Doc) -> tuple[bool, str]:
    """(통과 여부, 사유) — 사유는 'keep:이름' / 'drop:이름'."""
    title = doc.title
    unit = norm_unit(doc.unit_job)

    # 1) 강한 배제
    for name, rx in _HARD_DROP_TITLE:
        if rx.search(title):
            return False, f"drop:{name}"
    if unit:
        for name, rx in _HARD_DROP_UNIT:
            if rx.search(unit):
                return False, f"drop:{name}"
    if len(title) < 10:
        return False, "drop:너무짧음"

    # 2) 통과 조건
    for name, rx in _KEEP_TITLE:
        if rx.search(title):
            return True, f"keep:{name}"
    # 정책부서는 단독으로 통과시키지 않는다 — 약한 정책 어휘와 함께여야 한다
    if doc.dept and KEEP_DEPT.search(doc.dept) and WEAK_POLICY.search(title):
        return True, "keep:정책부서+어휘"

    # 3) 기본 배제
    return False, "drop:해당없음"


def apply(docs, stats: FilterStats | None = None):
    st = stats or FilterStats()
    for doc in docs:
        st.total += 1
        ok, reason = classify(doc)
        kind, _, name = reason.partition(":")
        if ok:
            st.kept += 1
            st.keep_hits[name] += 1
            yield doc
        else:
            st.dropped += 1
            st.drop_hits[name] += 1
