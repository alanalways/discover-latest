import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",        // 靜態輸出（FastAPI serve）
  distDir: "out",          // build 輸出目錄
  images: {
    unoptimized: true,     // 靜態模式不支援 Image Optimization
  },
};

export default nextConfig;
