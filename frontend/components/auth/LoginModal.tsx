"use client";

import React from 'react';
import { useAuth } from './AuthProvider';
import { X } from 'lucide-react';
import { createPkceSession } from '@/lib/pkce';

export default function LoginModal() {
    const { showLoginModal, setShowLoginModal } = useAuth();

    if (!showLoginModal) return null;

    const handleGoogleLogin = async () => {
        try {
            const callback = `${window.location.origin}/auth/callback`;
            const pkce = await createPkceSession();
            const params = new URLSearchParams({
                redirect_to: callback,
                state: pkce.state,
                code_challenge: pkce.codeChallenge,
                code_challenge_method: pkce.codeChallengeMethod,
            });
            const authStartUrl = `/api/auth/google/start?${params.toString()}`;
            window.location.href = authStartUrl;
        } catch {
            alert("登入失敗，請稍後再試");
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
            <div className="bg-gray-900 rounded-2xl border border-gray-700 w-full max-w-md p-8 relative shadow-2xl animate-in fade-in zoom-in-95 duration-200">
                <button
                    onClick={() => setShowLoginModal(false)}
                    className="absolute top-4 right-4 text-gray-500 hover:text-white transition"
                >
                    <X size={24} />
                </button>

                <div className="text-center mb-8">
                    <h2 className="text-3xl font-black mb-2 text-white">歡迎回來</h2>
                    <p className="text-gray-400">登入以解鎖更多強大功能</p>
                </div>

                <div className="space-y-4">
                    <button
                        onClick={handleGoogleLogin}
                        className="w-full py-4 bg-white text-gray-900 rounded-xl font-bold text-lg hover:bg-gray-100 transition flex items-center justify-center gap-3"
                    >
                        <svg className="w-6 h-6" viewBox="0 0 24 24">
                            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                        </svg>
                        使用 Google 帳號登入
                    </button>

                    <div className="relative my-6">
                        <div className="absolute inset-0 flex items-center">
                            <div className="w-full border-t border-gray-700"></div>
                        </div>
                        <div className="relative flex justify-center text-sm">
                            <span className="px-2 bg-gray-900 text-gray-500">或</span>
                        </div>
                    </div>

                    <div className="text-center text-gray-500 text-sm">
                        訪客可使用基本查詢功能。<br />
                        登入後可升級 Pro/Premium 獲得完整權限。
                    </div>
                </div>
            </div>
        </div>
    );
}
