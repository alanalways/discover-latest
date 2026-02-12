"use client";

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import api from '@/lib/api';

function AuthCallbackContent() {
    const searchParams = useSearchParams();
    const [message, setMessage] = useState('正在完成登入...');

    useEffect(() => {
        const code = searchParams.get('code');
        const queryToken = searchParams.get('access_token');
        const queryError = searchParams.get('error_description') || searchParams.get('error');
        const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
        const hashToken = hashParams.get('access_token');
        const tokenFromCallback = queryToken || hashToken;

        if (queryError) {
            const decoded = decodeURIComponent(queryError);
            if (decoded.includes('Unable to exchange external code')) {
                setMessage('登入失敗：Google OAuth 交換失敗（請檢查 Supabase 的 Google Client ID/Secret 與授權設定）');
            } else {
                setMessage(`登入失敗：${decoded}`);
            }
            return;
        }

        const finishLogin = async () => {
            try {
                if (tokenFromCallback) {
                    api.setToken(tokenFromCallback);
                    await api.getCurrentUser();
                    setMessage('登入成功，正在跳轉...');
                    window.location.href = '/';
                    return;
                }

                if (!code) {
                    throw new Error('缺少授權碼，請重新登入');
                }

                const res = await api.loginWithGoogleCode(code);
                if (!res.success || !res.access_token) {
                    throw new Error(res.message || 'OAuth 交換失敗');
                }
                api.setToken(res.access_token);
                setMessage('登入成功，正在跳轉...');
                window.location.href = '/';
            } catch (err) {
                console.error('OAuth callback failed:', err);
                setMessage('登入失敗，請返回首頁重新登入。');
            }
        };

        void finishLogin();
    }, [searchParams]);

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
