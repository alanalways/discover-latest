"use client";

import React, { useState } from 'react';
import Sidebar from '@/components/layout/Sidebar';
import Topbar from '@/components/layout/Topbar';
import RouteProgress from '@/components/layout/RouteProgress';
import AuthProvider from '@/components/auth/AuthProvider';
import LoginModal from '@/components/auth/LoginModal';
import ThemeProvider from '@/components/theme/ThemeProvider';

export default function ClientLayout({ children }: { children: React.ReactNode }) {
    const [sidebarOpen, setSidebarOpen] = useState(false);

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

                    <div className="dl-main">
                        <Topbar
                            onMenuClick={() => setSidebarOpen(true)}
                        />

                        <main className="dl-content" onClick={() => sidebarOpen && setSidebarOpen(false)}>
                            {children}
                        </main>
                    </div>

                    <LoginModal />
                </div>
            </ThemeProvider>
        </AuthProvider>
    );
}
