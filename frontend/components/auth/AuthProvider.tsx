"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';

interface User {
    id: string;
    email?: string;
    name: string;
    picture?: string;
    tier: 'free' | 'pro' | 'premium';
    createdAt?: string;
    investorProfile?: { type: string; name: string };
    userMetadata?: {
        full_name?: string;
        avatar_url?: string;
        tier?: 'free' | 'pro' | 'premium';
        is_admin?: boolean;
        role?: string;
        roles?: string[];
        investor_profile?: { type: string; name: string };
    };
    appMetadata?: {
        is_admin?: boolean;
        role?: string;
        roles?: string[];
    };
}

function normalizeUser(raw: unknown): User | null {
    if (!raw || typeof raw !== 'object') return null;
    const data = raw as {
        id?: string;
        email?: string;
        name?: string;
        tier?: 'free' | 'pro' | 'premium';
        created_at?: string;
        picture?: string;
        avatar_url?: string;
        user_metadata?: {
            full_name?: string;
            avatar_url?: string;
            tier?: 'free' | 'pro' | 'premium';
            is_admin?: boolean;
            role?: string;
            roles?: string[];
            investor_profile?: { type: string; name: string };
        };
        app_metadata?: {
            is_admin?: boolean;
            role?: string;
            roles?: string[];
        };
    };

    if (!data.id) return null;

    const metadata = data.user_metadata || {};
    const appMetadata = data.app_metadata || {};
    const tier = data.tier || metadata.tier || 'free';
    const name = data.name || metadata.full_name || data.email || '使用者';
    const picture = data.picture || data.avatar_url || metadata.avatar_url;
    const rawProfile = metadata.investor_profile;
    const investorProfile =
        rawProfile && typeof rawProfile === 'object' &&
        typeof (rawProfile as { type?: unknown }).type === 'string' &&
        typeof (rawProfile as { name?: unknown }).name === 'string'
            ? { type: (rawProfile as { type: string }).type, name: (rawProfile as { name: string }).name }
            : undefined;

    return {
        id: data.id,
        email: data.email,
        name,
        picture,
        tier,
        createdAt: data.created_at,
        investorProfile,
        userMetadata: metadata,
        appMetadata,
    };
}

interface AuthContextType {
    user: User | null;
    token: string | null;
    isLoggedIn: boolean;
    login: (token: string) => Promise<void>;
    logout: () => void;
    refreshUser: () => Promise<void>;
    showLoginModal: boolean;
    setShowLoginModal: (show: boolean) => void;
}

const AuthContext = createContext<AuthContextType>({
    user: null,
    token: null,
    isLoggedIn: false,
    login: async () => { },
    logout: () => { },
    refreshUser: async () => { },
    showLoginModal: false,
    setShowLoginModal: () => { },
});

export const useAuth = () => useContext(AuthContext);

export default function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [showLoginModal, setShowLoginModal] = useState(false);

    const clearAuthState = useCallback((redirectHome: boolean) => {
        setUser(null);
        setToken(null);
        api.setToken(null);
        if (typeof window !== 'undefined') {
            localStorage.removeItem('dl_token');
            if (redirectHome) {
                window.location.href = '/';
            }
        }
    }, []);

    const logout = useCallback(() => {
        clearAuthState(true);
    }, [clearAuthState]);

    const fetchUser = useCallback(async () => {
        try {
            const res = await api.getCurrentUser();
            const normalized = normalizeUser(res?.user);
            if (normalized) {
                setUser(normalized);
            } else {
                logout();
            }
        } catch (err) {
            console.error(err);
            logout();
        }
    }, [logout]);

    const refreshUser = useCallback(async () => {
        const currentToken = api.getToken();
        if (!currentToken) return;
        setToken(currentToken);
        api.setToken(currentToken);
        await fetchUser();
    }, [fetchUser]);

    // 初始化檢查 Token
    useEffect(() => {
        const storedToken = typeof window !== 'undefined' ? localStorage.getItem('dl_token') : null;
        if (!storedToken) return;
        setToken(storedToken);
        api.setToken(storedToken);
        void fetchUser();
    }, [fetchUser]);

    useEffect(() => {
        const onRefresh = () => { void refreshUser(); };
        window.addEventListener('dl:auth-refresh', onRefresh);
        return () => window.removeEventListener('dl:auth-refresh', onRefresh);
    }, [refreshUser]);

    useEffect(() => {
        const onAuthExpired = () => {
            clearAuthState(false);
            setShowLoginModal(true);
        };
        window.addEventListener('dl:auth-expired', onAuthExpired);
        return () => window.removeEventListener('dl:auth-expired', onAuthExpired);
    }, [clearAuthState]);

    const login = async (googleToken: string) => {
        try {
            const res = await api.loginWithGoogle(googleToken);
            if (res.success && res.user && res.access_token) {
                const normalized = normalizeUser(res.user);
                if (!normalized) {
                    throw new Error('登入成功但使用者資料無效');
                }
                setToken(res.access_token);
                api.setToken(res.access_token);
                setUser(normalized);
                setShowLoginModal(false);
                return;
            }
            if (res.success && res.user) {
                const normalized = normalizeUser(res.user);
                if (!normalized) {
                    throw new Error('登入成功但使用者資料無效');
                }
                setToken(googleToken);
                api.setToken(googleToken);
                setUser(normalized);
                setShowLoginModal(false);
                return;
            }
            throw new Error(res.message || '登入失敗');
        } catch (err) {
            console.error("Login failed", err);
            throw err;
        }
    };

    return (
        <AuthContext.Provider value={{
            user,
            token,
            isLoggedIn: !!user,
            login,
            logout,
            refreshUser,
            showLoginModal,
            setShowLoginModal
        }}>
            {children}
        </AuthContext.Provider>
    );
}
