"use client";

import React, { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'dark' | 'light';

interface ThemeContextType {
    theme: Theme;
    toggleTheme: () => void;
    fontScale: number;
    setFontScale: (scale: number) => void;
}

const ThemeContext = createContext<ThemeContextType>({
    theme: 'dark',
    toggleTheme: () => { },
    fontScale: 1,
    setFontScale: () => { },
});

export const useTheme = () => useContext(ThemeContext);

export default function ThemeProvider({ children }: { children: React.ReactNode }) {
    const [theme, setTheme] = useState<Theme>(() => {
        if (typeof window === 'undefined') return 'dark';
        const stored = localStorage.getItem('dl_theme');
        return stored === 'light' ? 'light' : 'dark';
    });
    const [fontScale, setFontScaleState] = useState<number>(() => {
        if (typeof window === 'undefined') return 1;
        const raw = Number(localStorage.getItem('dl_font_scale') || '1');
        if (!Number.isFinite(raw)) return 1;
        return Math.min(1.3, Math.max(0.85, raw));
    });

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        if (typeof window !== 'undefined') {
            localStorage.setItem('dl_theme', theme);
        }
    }, [theme]);

    useEffect(() => {
        document.documentElement.style.setProperty('--user-font-scale', String(fontScale));
        if (typeof window !== 'undefined') {
            localStorage.setItem('dl_font_scale', String(fontScale));
        }
    }, [fontScale]);

    const toggleTheme = () => {
        const newTheme = theme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
    };

    const setFontScale = (scale: number) => {
        const next = Math.min(1.3, Math.max(0.85, scale));
        setFontScaleState(Number(next.toFixed(2)));
    };

    return (
        <ThemeContext.Provider value={{ theme, toggleTheme, fontScale, setFontScale }}>
            {children}
        </ThemeContext.Provider>
    );
}
