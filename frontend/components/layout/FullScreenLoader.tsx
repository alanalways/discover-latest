'use client';

import { useEffect, useState } from 'react';
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
    // 退場動畫：visible 變 false 後先播動畫再移除 DOM
    const [mounted, setMounted] = useState(visible);
    const [exiting, setExiting] = useState(false);

    useEffect(() => {
        if (visible) {
            setMounted(true);
            setExiting(false);
        } else if (mounted) {
            // 開始退場動畫
            setExiting(true);
            const timer = setTimeout(() => {
                setMounted(false);
                setExiting(false);
            }, 350); // 配合 CSS overlayOut 動畫
            return () => clearTimeout(timer);
        }
    }, [visible, mounted]);

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
