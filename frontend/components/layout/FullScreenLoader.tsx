'use client';

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Activity } from 'lucide-react';
import styles from './FullScreenLoader.module.css';

interface FullScreenLoaderProps {
    /** 是否顯示全屏 loading */
    visible: boolean;
    /** 進度 0-100，若不傳則顯示不確定動畫 */
    progress?: number;
    /** 載入階段文字，如「正在取得市場指數…」 */
    message?: string;
}

/**
 * 全屏載入進度條
 * 遮蓋整個畫面，確保使用者不會看到過期/不確定的快取資料
 */
export default function FullScreenLoader({ visible, progress, message }: FullScreenLoaderProps) {
    // exitDone: true once the 350ms exit animation completes
    const [exitDone, setExitDone] = useState(!visible);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const startExitTimer = useCallback(() => {
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => {
            setExitDone(true);
            timerRef.current = null;
        }, 350);
    }, []);

    // When visible changes: if it just turned off, start exit timer
    useEffect(() => {
        if (!visible) {
            startExitTimer();
        }
        return () => {
            if (timerRef.current) clearTimeout(timerRef.current);
        };
    }, [visible, startExitTimer]);

    // When visible turns on, reset exit state immediately
    useLayoutEffect(() => {
        if (visible && exitDone) {
            setExitDone(false);
        }
    }, [visible, exitDone]);

    const mounted = visible || !exitDone;
    const exiting = !visible && !exitDone;

    if (!mounted) return null;

    const hasProgress = typeof progress === 'number';
    const pct = hasProgress ? Math.min(100, Math.max(0, progress)) : 0;

    return (
        <div className={`${styles.overlay} ${exiting ? styles.overlayOut : ''}`}>
            <div className={styles.loaderCard}>
                {/* Logo 動畫 */}
                <div className={styles.logoWrap}>
                    <Activity size={48} className={styles.logoIcon} />
                </div>

                {/* 進度條 */}
                <div className={styles.progressTrack}>
                    <div
                        className={`${styles.progressFill} ${!hasProgress ? styles.progressIndeterminate : ''}`}
                        style={hasProgress ? { width: `${pct}%` } : undefined}
                    />
                </div>

                {/* 訊息 + 百分比 */}
                {message && <p className={styles.message}>{message}</p>}
                {hasProgress && <span className={styles.percent}>{Math.round(pct)}%</span>}
            </div>
        </div>
    );
}
