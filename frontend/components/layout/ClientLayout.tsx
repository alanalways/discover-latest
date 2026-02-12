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
    const [collapsed, setCollapsed] = useState(false);
    const pathname = usePathname();

    // 計算 sidebar 寬度（數字）
    const sidebarWidth = collapsed ? 64 : 240;

    // 從 localStorage 讀取 collapsed 狀態
    useEffect(() => {
        const saved = localStorage.getItem('sidebar-collapsed');
        if (saved === 'true') setCollapsed(true);
    }, []);

    // 路由改變時關閉 mobile sidebar
    useEffect(() => {
        setSidebarOpen(false);
    }, [pathname]);

    const handleToggleCollapse = () => {
        const next = !collapsed;
        setCollapsed(next);
        localStorage.setItem('sidebar-collapsed', String(next));
    };

    return (
        <AuthProvider>
            <ThemeProvider>
                <div className="flex min-h-screen bg-[var(--bg-void)] text-[var(--text-1)]">
                    {/* Sidebar */}
                    <Sidebar
                        isOpen={sidebarOpen}
                        onClose={() => setSidebarOpen(false)}
                        collapsed={collapsed}
                    />

                    {/* Mobile Sidebar Overlay */}
                    {sidebarOpen && (
                        <div
                            className="fixed inset-0 bg-black/50 z-40 md:hidden backdrop-blur-sm animate-in fade-in"
                            onClick={() => setSidebarOpen(false)}
                        />
                    )}

                    {/* Main content area — 用 inline style 確保 production 也正確 */}
                    <div
                        className="flex-1 flex flex-col transition-all duration-300 relative w-full"
                        style={{ marginLeft: sidebarWidth }}
                    >
                        <Topbar
                            onMenuClick={() => setSidebarOpen(true)}
                            onToggleCollapse={handleToggleCollapse}
                            collapsed={collapsed}
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
