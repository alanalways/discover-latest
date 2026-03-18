'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import styles from './RouteProgress.module.css';

const START_EVENT = 'dl:route-progress-start';
const DONE_EVENT = 'dl:route-progress-done';

export function startRouteProgress() {
    if (typeof window === 'undefined') return;
    window.dispatchEvent(new Event(START_EVENT));
}

export function doneRouteProgress() {
    if (typeof window === 'undefined') return;
    window.dispatchEvent(new Event(DONE_EVENT));
}

function isInternalAnchor(target: EventTarget | null): HTMLAnchorElement | null {
    if (!(target instanceof Element)) return null;
    const anchor = target.closest('a[href]') as HTMLAnchorElement | null;
    if (!anchor) return null;
    const href = anchor.getAttribute('href') || '';
    if (!href || href.startsWith('#')) return null;
    if (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('mailto:')) return null;
    if (anchor.target === '_blank') return null;
    return anchor;
}

export default function RouteProgress() {
    const pathname = usePathname();
    const [visible, setVisible] = useState(false);
    const [progress, setProgress] = useState(0);
    const progressTimerRef = useRef<number | null>(null);
    const failSafeTimerRef = useRef<number | null>(null);
    const finishingRef = useRef(false);
    const pendingRef = useRef(0);

    const clearTimers = () => {
        if (progressTimerRef.current) {
            window.clearInterval(progressTimerRef.current);
            progressTimerRef.current = null;
        }
        if (failSafeTimerRef.current) {
            window.clearTimeout(failSafeTimerRef.current);
            failSafeTimerRef.current = null;
        }
    };

    const start = () => {
        clearTimers();
        finishingRef.current = false;
        setVisible(true);
        setProgress(12);
        progressTimerRef.current = window.setInterval(() => {
            setProgress((prev) => {
                if (prev >= 90) return prev;
                return prev + Math.max(1, Math.round((90 - prev) * 0.18));
            });
        }, 120);
        failSafeTimerRef.current = window.setTimeout(() => {
            finish();
        }, 8000);
    };

    const finish = () => {
        if (finishingRef.current) return;
        finishingRef.current = true;
        clearTimers();
        setProgress(100);
        window.setTimeout(() => {
            setVisible(false);
            setProgress(0);
            finishingRef.current = false;
        }, 220);
    };

    useEffect(() => {
        const onStart = () => {
            pendingRef.current += 1;
            start();
        };
        const onDone = () => {
            pendingRef.current = Math.max(0, pendingRef.current - 1);
            if (pendingRef.current === 0) {
                finish();
            }
        };
        const onClick = (e: MouseEvent) => {
            if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
            const anchor = isInternalAnchor(e.target);
            if (!anchor) return;
            start();
        };

        window.addEventListener(START_EVENT, onStart);
        window.addEventListener(DONE_EVENT, onDone);
        document.addEventListener('click', onClick, true);
        return () => {
            window.removeEventListener(START_EVENT, onStart);
            window.removeEventListener(DONE_EVENT, onDone);
            document.removeEventListener('click', onClick, true);
            clearTimers();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        if (visible) {
            pendingRef.current = 0;
            finish();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [pathname]);

    return (
        <div className={`${styles.progressWrap} ${visible ? styles.visible : ''}`} aria-hidden>
            <div className={styles.progressBar} style={{ width: `${progress}%` }} />
        </div>
    );
}
