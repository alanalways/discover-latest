'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';

const STORAGE_KEY_COMPLETED = 'dl_onboarding_completed';
const STORAGE_KEY_STEP = 'dl_onboarding_step';
const TOTAL_STEPS = 7;

interface OnboardingContextType {
    /** Whether the onboarding flow is currently active */
    isActive: boolean;
    /** Current step (1-based), 0 means inactive */
    currentStep: number;
    /** Total number of steps */
    totalSteps: number;
    /** Advance to the next step */
    next: () => void;
    /** Skip / dismiss the entire onboarding */
    skip: () => void;
    /** Restart onboarding (e.g. from settings) */
    restart: () => void;
}

const OnboardingContext = createContext<OnboardingContextType>({
    isActive: false,
    currentStep: 0,
    totalSteps: TOTAL_STEPS,
    next: () => { },
    skip: () => { },
    restart: () => { },
});

export function useOnboarding() {
    return useContext(OnboardingContext);
}

export const ONBOARDING_STEPS = [
    {
        step: 1,
        selector: '[data-onboarding="step-1"]',
        title: '儀表板',
        description: '市場總覽與熱門股票一目了然',
    },
    {
        step: 2,
        selector: '[data-onboarding="step-2"]',
        title: '自選清單',
        description: '追蹤你關注的股票，即時掌握動態',
    },
    {
        step: 3,
        selector: '[data-onboarding="step-3"]',
        title: '深度分析',
        description: 'AI 深度分析個股，提供進出場建議',
    },
    {
        step: 4,
        selector: '[data-onboarding="step-4"]',
        title: '回測模擬',
        description: '用歷史數據驗證你的投資策略',
    },
    {
        step: 5,
        selector: '[data-onboarding="step-5"]',
        title: '投資健檢',
        description: '檢視投資組合風險與配置建議',
    },
    {
        step: 6,
        selector: '[data-onboarding="step-6"]',
        title: 'AI 分析次數',
        description: '查看今日剩餘 AI 分析額度',
    },
    {
        step: 7,
        selector: '[data-onboarding="step-7"]',
        title: '投資風格測驗',
        description: '了解你的投資風格，獲得個人化建議',
        cta: { label: '前往測驗', href: '/quiz' },
    },
];

export default function OnboardingProvider({ children }: { children: React.ReactNode }) {
    const { isLoggedIn, isInitialized } = useAuth();
    const [currentStep, setCurrentStep] = useState(0);

    // On mount + login, check localStorage
    useEffect(() => {
        if (!isInitialized || !isLoggedIn) return;
        let cancelled = false;
        const applyStep = (step: number) => {
            window.setTimeout(() => {
                if (!cancelled) {
                    setCurrentStep(step);
                }
            }, 0);
        };
        try {
            const completed = localStorage.getItem(STORAGE_KEY_COMPLETED);
            if (completed === '1') {
                applyStep(0);
            } else {
                const saved = localStorage.getItem(STORAGE_KEY_STEP);
                const step = saved ? parseInt(saved, 10) : 1;
                applyStep(step >= 1 && step <= TOTAL_STEPS ? step : 1);
            }
        } catch {
            applyStep(1);
        }
        return () => {
            cancelled = true;
        };
    }, [isInitialized, isLoggedIn]);

    const next = useCallback(() => {
        setCurrentStep((prev) => {
            const nextStep = prev + 1;
            if (nextStep > TOTAL_STEPS) {
                try {
                    localStorage.setItem(STORAGE_KEY_COMPLETED, '1');
                    localStorage.removeItem(STORAGE_KEY_STEP);
                } catch { /* ignore */ }
                return 0;
            }
            try { localStorage.setItem(STORAGE_KEY_STEP, String(nextStep)); } catch { /* ignore */ }
            return nextStep;
        });
    }, []);

    const skip = useCallback(() => {
        setCurrentStep(0);
        try {
            localStorage.setItem(STORAGE_KEY_COMPLETED, '1');
            localStorage.removeItem(STORAGE_KEY_STEP);
        } catch { /* ignore */ }
    }, []);

    const restart = useCallback(() => {
        try {
            localStorage.removeItem(STORAGE_KEY_COMPLETED);
            localStorage.setItem(STORAGE_KEY_STEP, '1');
        } catch { /* ignore */ }
        setCurrentStep(1);
    }, []);

    const isActive = currentStep >= 1 && currentStep <= TOTAL_STEPS;

    const value = useMemo(() => ({
        isActive,
        currentStep,
        totalSteps: TOTAL_STEPS,
        next,
        skip,
        restart,
    }), [isActive, currentStep, next, skip, restart]);

    return (
        <OnboardingContext.Provider value={value}>
            {children}
        </OnboardingContext.Provider>
    );
}
