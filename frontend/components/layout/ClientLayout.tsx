"use client";

import React, { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import Sidebar from '@/components/layout/Sidebar';
import Topbar from '@/components/layout/Topbar';
import RouteProgress from '@/components/layout/RouteProgress';
import AuthProvider, { useAuth } from '@/components/auth/AuthProvider';
import LoginModal from '@/components/auth/LoginModal';
import AuthGate from '@/components/auth/AuthGate';
import ThemeProvider from '@/components/theme/ThemeProvider';

function GatedShell({ children }: { children: React.ReactNode }) {
    const { isLoggedIn, isInitialized } = useAuth();
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const pathname = usePathname();
    const isPublicPath = pathname.startsWith('/auth/');
    const shouldGate = isInitialized && !isLoggedIn && !isPublicPath;

    useEffect(() => {
        if (sidebarOpen) {
            document.body.classList.add('dl-sidebar-open');
        } else {
            document.body.classList.remove('dl-sidebar-open');
        }
        return () => {
            document.body.classList.remove('dl-sidebar-open');
        };
    }, [sidebarOpen]);

    if (!isInitialized) {
        return <div className="dl-init-loading" />;
    }

    return (
        <div className="dl-shell">
            <RouteProgress />
            <Sidebar
                isOpen={sidebarOpen}
                onClose={() => setSidebarOpen(false)}
            />

            {sidebarOpen && (
                <div
                    className="dl-mobile-overlay"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            <div className={`dl-main ${sidebarOpen ? 'dl-main-locked' : ''}`}>
                <Topbar
                    onMenuClick={() => setSidebarOpen(true)}
                />

                <main className="dl-content">
                    <div
                        key={pathname}
                        className={`dl-content-view${shouldGate ? ' dl-gated' : ''}`}
                    >
                        {children}
                    </div>
                    {shouldGate && <AuthGate />}
                </main>
            </div>

            <LoginModal />
        </div>
    );
}

export default function ClientLayout({ children }: { children: React.ReactNode }) {
    return (
        <AuthProvider>
            <ThemeProvider>
                <GatedShell>{children}</GatedShell>
            </ThemeProvider>
        </AuthProvider>
    );
}
