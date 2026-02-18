import type { Metadata } from 'next';
import Script from 'next/script';
import './globals.css';
import ClientLayout from '@/components/layout/ClientLayout';

export const metadata: Metadata = {
  title: 'DiscoverLatest — AI 智慧投資分析平台',
  description: '整合 SMC/ICT 技術分析、AI 深度研究與即時市場資訊的金融分析平台',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW">
      <head>
        {/* Google Fonts preconnect — 提前建立連線，減少字體載入延遲 */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Exo+2:wght@300;400;500;600;700&family=Orbitron:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        {/* 專案大量使用 utility class，部署端提供 runtime Tailwind 相容層 */}
        <Script src="https://cdn.tailwindcss.com" strategy="beforeInteractive" />
      </head>
      <body>
        <ClientLayout>
          {children}
        </ClientLayout>
      </body>
    </html>
  );
}
