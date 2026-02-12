"use client";

import React, { useState, useEffect } from 'react';
import Sidebar from '@/components/layout/Sidebar';
import Topbar from '@/components/layout/Topbar';
import AuthProvider from '@/components/auth/AuthProvider';
import LoginModal from '@/components/auth/LoginModal';
import ThemeProvider from '@/components/theme/ThemeProvider';
import { usePathname } from 'next/navigation';

export default function ClientLayout({ children }: { children: React.ReactNode }) {
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const pathname = usePathname();

    // 固定 sidebar 寬度 240px（不再支援 collapse）
    const sidebarWidth = 240;

    // 路由改變時關閉 mobile sidebar
    useEffect(() => {
        setSidebarOpen(false);
    }, [pathname]);

    return (
        <AuthProvider>
            <ThemeProvider>
                <div className="flex min-h-screen bg-[var(--bg-void)] text-[var(--text-1)]">
                    {/* Sidebar — 固定展開 */}
                    <Sidebar
                        isOpen={sidebarOpen}
                        onClose={() => setSidebarOpen(false)}
                    />

                    {/* Mobile Sidebar Overlay */}
                    {sidebarOpen && (
                        <div
                            className="fixed inset-0 bg-black/50 z-40 md:hidden backdrop-blur-sm animate-in fade-in"
                            onClick={() => setSidebarOpen(false)}
                        />
                    )}

                    {/* Main content area */}
                    <div
                        className="flex-1 flex flex-col transition-all duration-300 relative w-full"
                        style={{ marginLeft: sidebarWidth }}
                    >
                        <Topbar
                            onMenuClick={() => setSidebarOpen(true)}
                            sidebarWidth={sidebarWidth}
                        />

                        <main className="flex-1 p-4 md:p-8 mt-[var(--topbar-h)] overflow-x-hidden">
                            {children}
                        </main>
                    </div>

                    <LoginModal />
                </div>
            </ThemeProvider>
        </AuthProvider>
    );
}
