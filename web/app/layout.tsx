import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "정책 동향 리포트",
  description:
    "중앙행정기관이 공개한 행정문서를 수집·분석해 1장으로 종합한 리포트입니다.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-stone-50 text-stone-900 antialiased dark:bg-stone-950 dark:text-stone-100">
        <header className="border-b border-stone-200 bg-white/80 backdrop-blur dark:border-stone-800 dark:bg-stone-900/80">
          <div className="mx-auto flex max-w-4xl items-baseline gap-3 px-5 py-4">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              정책 동향 리포트
            </Link>
            <span className="text-sm text-stone-500 dark:text-stone-400">
              중앙행정기관 공개문서 종합
            </span>
          </div>
        </header>

        <main className="mx-auto max-w-4xl px-5 py-8">{children}</main>

        <footer className="mx-auto max-w-4xl px-5 pb-12 pt-4 text-xs leading-relaxed text-stone-500 dark:text-stone-400">
          <p>
            공공기관이 정보공개법에 따라 공개한 원문정보 목록을 수집·분석합니다.
            분석 결과는 <strong>초안</strong>이며 최종 판단은 사람이 합니다.
            반드시 근거 원문을 함께 확인하세요.
          </p>
        </footer>
      </body>
    </html>
  );
}
