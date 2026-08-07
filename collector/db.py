"""저장 계층 — SQLite.

기획서 Ⅱ-2의 3계층 중 L0 / L0b / L1 을 담당한다.
전건은 저장하지 않는다. 카운터만 올리고 버린다.

로컬은 stdlib sqlite3, 배포는 Turso(libsql)로 바꿔 끼운다.
스키마와 쿼리는 동일하다.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from typing import Iterable

from .client import Doc

SCHEMA = """
-- L0: 일자 × 기관 총건수. 급증 판정의 분모.
CREATE TABLE IF NOT EXISTS daily_counts (
    date        TEXT NOT NULL,
    instt_se    TEXT NOT NULL,   -- C/W/B/E/P
    org         TEXT NOT NULL DEFAULT '',
    total       INTEGER NOT NULL,
    PRIMARY KEY (date, instt_se, org)
);

-- L0b: 키워드 × 일자 × 기관 집계. 급증 판정의 분자.
CREATE TABLE IF NOT EXISTS keyword_daily (
    date        TEXT NOT NULL,
    keyword     TEXT NOT NULL,
    org         TEXT NOT NULL,
    cnt         INTEGER NOT NULL,
    PRIMARY KEY (date, keyword, org)
);
CREATE INDEX IF NOT EXISTS idx_kw_date ON keyword_daily(keyword, date);

-- L1: 필터를 통과한 문서만.
CREATE TABLE IF NOT EXISTS docs (
    doc_key     TEXT PRIMARY KEY,
    date        TEXT NOT NULL,
    title       TEXT NOT NULL,
    org         TEXT NOT NULL,
    dept        TEXT NOT NULL,
    org_code    TEXT NOT NULL DEFAULT '',
    unit_job    TEXT NOT NULL DEFAULT '',
    theme       TEXT NOT NULL DEFAULT '',
    doc_no      TEXT NOT NULL DEFAULT '',
    open_type   TEXT NOT NULL DEFAULT '',
    produced_at TEXT NOT NULL DEFAULT '',
    keywords    TEXT NOT NULL DEFAULT ''   -- 개행 구분
);
CREATE INDEX IF NOT EXISTS idx_docs_date ON docs(date);
CREATE INDEX IF NOT EXISTS idx_docs_org  ON docs(org, date);

-- L2: 발행 신호. 배치가 쓰고 웹사이트가 읽는다.
-- (운영 단계에서는 이 테이블이 Airtable로 간다. 스키마는 같게 유지한다.)
CREATE TABLE IF NOT EXISTS signals (
    signal_id   TEXT PRIMARY KEY,
    keyword     TEXT NOT NULL,
    shared_terms TEXT NOT NULL DEFAULT '',  -- 문서 절반 이상이 공유하는 키워드
    cohesion    INTEGER NOT NULL DEFAULT 0, -- 공유 키워드 수 = 클러스터 응집도
    title       TEXT NOT NULL,       -- 대표 문서 제목. 운영에선 AI가 다듬는다
    summary     TEXT NOT NULL DEFAULT '',
    signal_type TEXT NOT NULL,       -- 동시다발 / 급증 / 신규등장
    strength    INTEGER NOT NULL,    -- 1~5 정수. 0·소수점 금지
    doc_count   INTEGER NOT NULL,
    org_count   INTEGER NOT NULL,
    orgs        TEXT NOT NULL DEFAULT '',   -- 개행 구분
    source_docs TEXT NOT NULL DEFAULT '',   -- JSON 배열
    period_from TEXT NOT NULL DEFAULT '',
    period_to   TEXT NOT NULL DEFAULT '',
    detected_at TEXT NOT NULL,
    published   INTEGER NOT NULL DEFAULT 0, -- 사람 검수 전에는 0
    sent_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_sig_pub ON signals(published, detected_at DESC);

-- 1장짜리 종합 리포트. 기간 전체를 AI가 총평한 것.
CREATE TABLE IF NOT EXISTS briefings (
    brief_id    TEXT PRIMARY KEY,   -- 기간 기준 id (from_to)
    period_from TEXT NOT NULL,
    period_to   TEXT NOT NULL,
    headline    TEXT NOT NULL DEFAULT '',
    overview    TEXT NOT NULL DEFAULT '',   -- 전체 총평
    by_category TEXT NOT NULL DEFAULT '',   -- JSON: [{category, note, count}]
    watch       TEXT NOT NULL DEFAULT '',   -- JSON: 눈여겨볼 사안 id 목록
    doc_total   INTEGER NOT NULL DEFAULT 0,
    signal_total INTEGER NOT NULL DEFAULT 0,
    model       TEXT NOT NULL DEFAULT '',
    generated_at TEXT NOT NULL
);

-- 수집 실행 기록. 어느 날짜를 언제 어떻게 수집했는지.
CREATE TABLE IF NOT EXISTS runs (
    date        TEXT NOT NULL,
    instt_se    TEXT NOT NULL,
    scanned     INTEGER NOT NULL,   -- 훑은 건수
    kept        INTEGER NOT NULL,   -- 저장한 건수
    drop_rate   REAL    NOT NULL,
    finished_at TEXT NOT NULL,
    PRIMARY KEY (date, instt_se)
);
"""


class Store:
    def __init__(self, path: str | Path = "data/signals.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """이미 있는 테이블에 새 컬럼을 더한다.

        `CREATE TABLE IF NOT EXISTS` 는 기존 테이블을 건드리지 않으므로
        스키마를 늘릴 때는 여기에 한 줄 추가한다.
        **DB 파일을 지우는 것으로 해결하지 말 것** — 수집 데이터가 날아간다.
        """
        additions = {
            "signals": [
                ("shared_terms", "TEXT NOT NULL DEFAULT ''"),
                ("cohesion", "INTEGER NOT NULL DEFAULT 0"),
                # AI 해석 결과. 통계 결과(title/summary)와 **분리해서** 담는다.
                # 어디까지가 관측이고 어디부터가 해석인지 화면에서 구분하기 위함.
                ("ai_title", "TEXT NOT NULL DEFAULT ''"),
                ("ai_summary", "TEXT NOT NULL DEFAULT ''"),
                ("ai_impact", "TEXT NOT NULL DEFAULT ''"),
                ("ai_category", "TEXT NOT NULL DEFAULT ''"),
                ("ai_model", "TEXT NOT NULL DEFAULT ''"),
                ("ai_generated_at", "TEXT NOT NULL DEFAULT ''"),
                # 정형 반복 업무인지에 대한 AI 판단.
                # 응집도만으로 줄 세우면 정형 문서가 상위를 차지한다 —
                # 제목이 서로 닮은 것이 정형 문서의 특징이기 때문이다.
                ("ai_routine", "INTEGER NOT NULL DEFAULT 0"),
                ("ai_notability", "INTEGER NOT NULL DEFAULT 0"),  # 1~5
            ],
        }
        for table, cols in additions.items():
            have = {
                r["name"]
                for r in self.conn.execute(f"PRAGMA table_info({table})")
            }
            if not have:  # 테이블 자체가 없으면 SCHEMA가 이미 만들었을 것
                continue
            for name, decl in cols:
                if name not in have:
                    self.conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {decl}"
                    )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.conn.commit()
        self.close()

    # -- L0 -----------------------------------------------------------------
    def record_daily_total(self, date: str, instt_se: str, total: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO daily_counts(date, instt_se, org, total) "
            "VALUES (?,?,'',?)",
            (date, instt_se, total),
        )

    def record_org_counts(self, date: str, instt_se: str, counts: Counter) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO daily_counts(date, instt_se, org, total) "
            "VALUES (?,?,?,?)",
            [(date, instt_se, org, n) for org, n in counts.items()],
        )

    # -- L0b ----------------------------------------------------------------
    def record_keywords(self, date: str, counts: Counter) -> None:
        """counts 키는 (keyword, org) 튜플."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO keyword_daily(date, keyword, org, cnt) "
            "VALUES (?,?,?,?)",
            [(date, kw, org, n) for (kw, org), n in counts.items()],
        )

    # -- L1 -----------------------------------------------------------------
    def save_docs(self, docs: Iterable[Doc]) -> int:
        rows = [
            (
                d.doc_key, d.date, d.title, d.org, d.dept, d.org_code,
                d.unit_job, d.theme, d.doc_no, d.open_type, d.produced_at,
                "\n".join(d.keywords),
            )
            for d in docs
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO docs(doc_key, date, title, org, dept, org_code,"
            " unit_job, theme, doc_no, open_type, produced_at, keywords)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        return len(rows)

    # -- L2 -----------------------------------------------------------------
    def save_signals(self, rows: list[dict]) -> int:
        """신호를 덮어쓴다. published 는 사람이 켠 값이므로 보존한다."""
        kept = {
            r["signal_id"]
            for r in self.conn.execute("SELECT signal_id FROM signals WHERE published=1")
        }
        self.conn.executemany(
            "INSERT OR REPLACE INTO signals(signal_id, keyword, shared_terms,"
            " cohesion, title, summary, signal_type, strength, doc_count,"
            " org_count, orgs, source_docs, period_from, period_to,"
            " detected_at, published, sent_at)"
            " VALUES (:signal_id,:keyword,:shared_terms,:cohesion,:title,:summary,"
            " :signal_type,:strength,:doc_count,:org_count,:orgs,:source_docs,"
            " :period_from,:period_to,:detected_at,:published,NULL)",
            [{**r, "published": 1 if r["signal_id"] in kept else 0} for r in rows],
        )
        return len(rows)

    # -- 실행 기록 ------------------------------------------------------------
    def record_run(
        self, date: str, instt_se: str, scanned: int, kept: int,
        drop_rate: float, finished_at: str,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO runs(date, instt_se, scanned, kept, drop_rate,"
            " finished_at) VALUES (?,?,?,?,?,?)",
            (date, instt_se, scanned, kept, drop_rate, finished_at),
        )

    def already_done(self, date: str, instt_se: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM runs WHERE date=? AND instt_se=?", (date, instt_se)
        )
        return cur.fetchone() is not None
