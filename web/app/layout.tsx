import type { Metadata } from "next";
import { stats } from "@/lib/data";
import "./globals.css";

export const metadata: Metadata = {
  title: "정책 동향 리포트",
  description:
    "중앙행정기관이 공개한 행정문서를 매일 수집·분석해 1장으로 종합한 리포트입니다.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <header className="masthead">
          <div className="shell masthead-in">
            <a href="/" className="title">
              정책 동향 리포트
            </a>
            <span className="sub">중앙행정기관 공개문서 종합</span>
            <span className="live">매일 02:00 갱신</span>
          </div>
        </header>

        <main className="shell">{children}</main>

        <footer className="foot">
          <div className="shell">
            <p style={{ margin: 0 }}>
              공공기관이 정보공개법에 따라 공개한 원문정보 목록을 수집·분석합니다.
              분석은 <strong>초안</strong>이며 최종 판단은 사람이 합니다.
              반드시 근거 원문을 함께 확인하세요.
            </p>
            <p style={{ margin: "6px 0 0" }}>
              {stats.scanned.toLocaleString()}건 수집 · {stats.kept.toLocaleString()}건 분석 ·{" "}
              <a
                href="https://www.open.go.kr/othicInfo/infoList/infoList.do"
                target="_blank"
                rel="noopener noreferrer"
              >
                정보공개포털
              </a>{" "}
              ·{" "}
              <a
                href="https://github.com/themoka7/trends"
                target="_blank"
                rel="noopener noreferrer"
              >
                소스
              </a>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
