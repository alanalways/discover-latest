'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useOnboarding, ONBOARDING_STEPS } from './OnboardingProvider';
import styles from './FeatureTooltip.module.css';

interface Position {
    top: number;
    left: number;
    width: number;
    height: number;
}

export default function FeatureTooltip() {
    const { isActive, currentStep, totalSteps, next, skip } = useOnboarding();
    const router = useRouter();
    const [targetPos, setTargetPos] = useState<Position | null>(null);
    const tooltipRef = useRef<HTMLDivElement>(null);
    const rafRef = useRef<number>(0);

    const stepConfig = isActive ? ONBOARDING_STEPS[currentStep - 1] : null;

    const updatePosition = useCallback(() => {
        if (!stepConfig) {
            setTargetPos(null);
            return;
        }
        const el = document.querySelector(stepConfig.selector);
        if (!el) {
            setTargetPos(null);
            return;
        }
        const rect = el.getBoundingClientRect();
        setTargetPos({
            top: rect.top,
            left: rect.left,
            width: rect.width,
            height: rect.height,
        });
    }, [stepConfig]);

    useEffect(() => {
        if (!isActive) return;
        // Small delay to let DOM settle after navigation
        const timer = setTimeout(updatePosition, 200);
        const onResize = () => {
            cancelAnimationFrame(rafRef.current);
            rafRef.current = requestAnimationFrame(updatePosition);
        };
        window.addEventListener('resize', onResize);
        window.addEventListener('scroll', onResize, true);
        return () => {
            clearTimeout(timer);
            cancelAnimationFrame(rafRef.current);
            window.removeEventListener('resize', onResize);
            window.removeEventListener('scroll', onResize, true);
        };
    }, [isActive, currentStep, updatePosition]);

    const handleNext = useCallback(() => {
        if (stepConfig?.cta) {
            skip();
            router.push(stepConfig.cta.href);
            return;
        }
        next();
    }, [stepConfig, next, skip, router]);

    if (!isActive || !stepConfig) return null;

    const spotlightStyle = targetPos
        ? {
              top: targetPos.top - 6,
              left: targetPos.left - 6,
              width: targetPos.width + 12,
              height: targetPos.height + 12,
          }
        : undefined;

    // Position tooltip below target, or above if too low
    const tooltipStyle: React.CSSProperties = {};
    if (targetPos) {
        const below = targetPos.top + targetPos.height + 16;
        const fitsBelow = below + 180 < window.innerHeight;
        tooltipStyle.top = fitsBelow ? below : targetPos.top - 180;
        tooltipStyle.left = Math.max(16, Math.min(targetPos.left, window.innerWidth - 340));
    } else {
        tooltipStyle.top = '50%';
        tooltipStyle.left = '50%';
        tooltipStyle.transform = 'translate(-50%, -50%)';
    }

    return (
        <div className={styles.overlay}>
            {/* Spotlight cutout */}
            {targetPos && <div className={styles.spotlight} style={spotlightStyle} />}

            {/* Tooltip card */}
            <div ref={tooltipRef} className={styles.tooltip} style={tooltipStyle}>
                <div className={styles.stepIndicator}>
                    {currentStep} / {totalSteps}
                </div>
                <h3 className={styles.title}>{stepConfig.title}</h3>
                <p className={styles.description}>{stepConfig.description}</p>
                <div className={styles.actions}>
                    <button className={styles.skipBtn} onClick={skip}>
                        跳過全部
                    </button>
                    <button className={styles.nextBtn} onClick={handleNext}>
                        {stepConfig.cta ? stepConfig.cta.label : currentStep === totalSteps ? '完成' : '下一步'}
                    </button>
                </div>
                {/* Progress dots */}
                <div className={styles.dots}>
                    {Array.from({ length: totalSteps }, (_, i) => (
                        <span
                            key={i}
                            className={`${styles.dot} ${i + 1 === currentStep ? styles.dotActive : ''} ${i + 1 < currentStep ? styles.dotDone : ''}`}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
}
