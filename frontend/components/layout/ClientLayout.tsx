"use client";

import React, { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import Sidebar from '@/components/layout/Sidebar';
import Topbar from '@/components/layout/Topbar';
import RouteProgress from '@/components/layout/RouteProgress';
import AuthProvider from '@/components/auth/AuthProvider';
import LoginModal from '@/components/auth/LoginModal';
import ThemeProvider from '@/components/theme/ThemeProvider';

export default function ClientLayout({ children }: { children: React.ReactNode }) {
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const pathname = usePathname();

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

    return (
        <AuthProvider>
            <ThemeProvider>
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
                            <div key={pathname} className="dl-content-view">
                                {children}
                            </div>
                        </main>
                    </div>

                    <LoginModal />
                </div>
            </ThemeProvider>
        </AuthProvider>
    );
}
