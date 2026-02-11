import type { Metadata } from 'next';
import './globals.css';
import Sidebar from '@/components/layout/Sidebar';
import Topbar from '@/components/layout/Topbar';

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
      <body>
        <Sidebar />
        <Topbar />
        <main
          style={{
            marginLeft: 'var(--sidebar-w)',
            marginTop: 'var(--topbar-h)',
            padding: '24px 32px 48px',
            minHeight: 'calc(100vh - var(--topbar-h))',
            background: 'var(--bg-void)',
          }}
        >
          {children}
        </main>
      </body>
    </html>
  );
}
