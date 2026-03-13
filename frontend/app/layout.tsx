import type { Metadata } from 'next';
import { Exo_2, Orbitron } from 'next/font/google';
import Script from 'next/script';
import './globals.css';
import ClientLayout from '@/components/layout/ClientLayout';

const exo2 = Exo_2({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-exo2',
  display: 'swap',
});

const orbitron = Orbitron({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-orbitron',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'DiscoverLatest — AI 智慧投資分析平台',
  description: '整合 SMC/ICT 技術分析、AI 深度研究與即時市場資訊的金融分析平台',
  viewport: 'width=device-width, initial-scale=1, maximum-scale=5',
  robots: 'index, follow',
  openGraph: {
    title: 'DiscoverLatest — AI 智慧投資分析平台',
    description: '整合 SMC/ICT 技術分析、AI 深度研究與即時市場資訊的金融分析平台',
    type: 'website',
    siteName: 'DiscoverLatest',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'DiscoverLatest — AI 智慧投資分析平台',
    description: '整合 SMC/ICT 技術分析、AI 深度研究與即時市場資訊的金融分析平台',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW" className={`${exo2.variable} ${orbitron.variable}`}>
      <head>
        <Script src="https://cdn.tailwindcss.com" strategy="afterInteractive" />
      </head>
      <body>
        <ClientLayout>
          {children}
        </ClientLayout>
      </body>
    </html>
  );
}
