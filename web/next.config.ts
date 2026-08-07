import type { NextConfig } from "next";

/**
 * GitHub Pages 정적 배포 설정.
 *
 * 프로젝트 저장소(`github.com/유저/저장소`)로 배포하면 주소가
 * `유저.github.io/저장소` 라서 basePath 가 필요하다.
 * Actions 워크플로가 저장소 이름을 NEXT_PUBLIC_BASE_PATH 로 넣어 준다.
 *
 * 로컬 개발에서는 비어 있으므로 http://localhost:3000 그대로 동작한다.
 */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  basePath,
  assetPrefix: basePath || undefined,
  // GitHub Pages 는 /path 를 /path/index.html 로 찾는다.
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
