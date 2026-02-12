"use client";

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import api from '@/lib/api';

function AuthCallbackContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const [message, setMessage] = useState('正在完成登入...');

    useEffect(() => {
        const code = searchParams.get('code');
        if (!code) {
            setMessage('登入失敗：缺少授權碼，請重新嘗試。');
            return;
        }

        const finishLogin = async () => {
            try {
                const res = await api.loginWithGoogleCode(code);
                if (!res.success || !res.access_token) {
                    throw new Error(res.message || 'OAuth 交換失敗');
                }
                api.setToken(res.access_token);
                setMessage('登入成功，正在跳轉...');
                router.replace('/');
            } catch (err) {
                console.error('OAuth callback failed:', err);
                setMessage('登入失敗，請返回首頁重新登入。');
            }
        };

        void finishLogin();
    }, [router, searchParams]);

    return (
        <div style={{
            minHeight: '60vh',
            display: 'grid',
            placeItems: 'center',
            color: 'var(--text-1)',
        }}>
            <div style={{
                padding: '24px 28px',
                border: '1px solid var(--border)',
                borderRadius: '12px',
                background: 'var(--bg-card)',
                fontSize: 14,
            }}>
                {message}
            </div>
        </div>
    );
}

export default function AuthCallbackPage() {
    return (
        <Suspense fallback={
            <div style={{
                minHeight: '60vh',
                display: 'grid',
                placeItems: 'center',
                color: 'var(--text-1)',
            }}>
                正在載入登入資訊...
            </div>
        }>
            <AuthCallbackContent />
        </Suspense>
    );
}
