"use client";

import React, { createContext, useContext, useState, useEffect } from 'react';
import { api } from '@/lib/api';

interface User {
    id: string;
    email: string;
    name: string;
    picture?: string;
    tier?: string; // free, pro, premium
}

interface AuthContextType {
    user: User | null;
    token: string | null;
    isLoggedIn: boolean;
    login: (token: string) => Promise<void>;
    logout: () => void;
    showLoginModal: boolean;
    setShowLoginModal: (show: boolean) => void;
}

const AuthContext = createContext<AuthContextType>({
    user: null,
    token: null,
    isLoggedIn: false,
    login: async () => { },
    logout: () => { },
    showLoginModal: false,
    setShowLoginModal: () => { },
});

export const useAuth = () => useContext(AuthContext);

export default function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [showLoginModal, setShowLoginModal] = useState(false);

    // 初始化檢查 Token
    useEffect(() => {
        const storedToken = localStorage.getItem('dl_token');
        if (storedToken) {
            setToken(storedToken);
            api.setToken(storedToken);
            fetchUser();
        }
    }, []);

    const fetchUser = async () => {
        try {
            const res = await api.getCurrentUser() as any;
            if (res && res.user) {
                setUser(res.user);
            } else {
                logout(); // Token 無效
            }
        } catch (err) {
            console.error(err);
            logout();
        }
    };

    const login = async (googleToken: string) => {
        try {
            const res = await api.loginWithGoogle(googleToken);
            if (res.success && res.user) {
                const newToken = (res as any).token || googleToken; // 假設後端回傳 JWT，或直接用 google token
                // 注意：實際上後端 /auth/google 應該回傳自己的 JWT
                // 這裡暫時假設 loginWithGoogle 會設定好 cookie 或回傳 token
                // 如果後端只是驗證，我們可能需要調整。
                // 根據 api.ts: return res.json()

                // 假設 res 包含 token
                const backendToken = (res as any).access_token || googleToken;

                setToken(backendToken);
                api.setToken(backendToken);
                setUser(res.user as User);
                setShowLoginModal(false);
            }
        } catch (err) {
            console.error("Login failed", err);
            throw err;
        }
    };

    const logout = () => {
        setUser(null);
        setToken(null);
        api.setToken(null);
        localStorage.removeItem('dl_token');
        window.location.href = '/'; // 重導回首頁
    };

    return (
        <AuthContext.Provider value={{
            user,
            token,
            isLoggedIn: !!user,
            login,
            logout,
            showLoginModal,
            setShowLoginModal
        }}>
            {children}
        </AuthContext.Provider>
    );
}
