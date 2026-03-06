'use client';

import { useState, useRef, useEffect } from 'react';
import { MessageSquare, Send, Loader2, Bot, User, ExternalLink } from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import styles from '../shared.module.css';

interface Source {
    title: string;
    uri: string;
}

interface Message {
    id: string;
    role: 'user' | 'ai';
    content: string;
    sources?: Source[];
    timestamp: Date;
}

export default function ChatPage() {
    const { isLoggedIn, setShowLoginModal } = useAuth();
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [symbol, setSymbol] = useState('');
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const sendMessage = async () => {
        if (!input.trim() || loading) return;
        if (!isLoggedIn) { setShowLoginModal(true); return; }

        const userMsg: Message = { id: Date.now().toString(), role: 'user', content: input.trim(), timestamp: new Date() };
        setMessages(prev => [...prev, userMsg]);
        const currentInput = input.trim();
        setInput('');
        setLoading(true);

        try {
            // 嘗試從訊息中偵測股票代號（排除常見金融術語）
            const NON_STOCK = new Set([
                'FED', 'GDP', 'CPI', 'PPI', 'NFP', 'FOMC', 'PCE', 'PMI', 'IPO', 'ETF',
                'AI', 'EPS', 'PE', 'PER', 'ROE', 'ROA', 'YOY', 'QOQ', 'USD', 'TWD',
                'EUR', 'JPY', 'CNY', 'GBP', 'BPS', 'CEO', 'CFO', 'CTO', 'SEC', 'ECB',
                'BOJ', 'IMF', 'WTO', 'API', 'ESG', 'SPX', 'DXY', 'VIX',
            ]);
            const numMatch = currentInput.match(/(?:^|\s)(\d{4})(?:\s|$)/);
            const alphaMatch = currentInput.toUpperCase().match(/(?:^|\s)([A-Z]{2,5})(?:\s|$)/);
            const candidate = numMatch ? numMatch[1]
                : (alphaMatch && !NON_STOCK.has(alphaMatch[1])) ? alphaMatch[1]
                : '';
            const detectedSymbol = candidate || symbol;
            if (detectedSymbol && !symbol) setSymbol(detectedSymbol);

            // 呼叫 Gemini with Google Search grounding
            const res = await api.fetch<{
                answer: string;
                sources?: Source[];
                symbol?: string;
            }>('/api/chat/ask', {
                method: 'POST',
                body: JSON.stringify({
                    message: currentInput,
                    symbol: detectedSymbol || '',
                }),
            });

            const aiMsg: Message = {
                id: (Date.now() + 1).toString(),
                role: 'ai',
                content: res.answer || 'AI 無法回應，請稍後重試。',
                sources: res.sources,
                timestamp: new Date(),
            };
            setMessages(prev => [...prev, aiMsg]);
        } catch (err: unknown) {
            const errorMsg = err instanceof Error ? err.message : 'AI 回應失敗';
            setMessages(prev => [...prev, {
                id: (Date.now() + 1).toString(),
                role: 'ai',
                content: `❌ ${errorMsg}`,
                timestamp: new Date(),
            }]);
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    };

    return (
        <div className={styles.container}>
            <div className={styles.panel} style={{ padding: '12px 24px' }}>
                <h3 className={styles.panelTitle} style={{ marginBottom: 0 }}>
                    <Bot size={18} /> AI 研究助手
                    <span style={{ fontSize: 11, color: 'var(--text-3)', marginLeft: 8, fontWeight: 400 }}>
                        Powered by DiscoverLatest
                    </span>
                    {symbol && <span style={{ fontSize: 12, color: 'var(--accent)', marginLeft: 8 }}>分析中: {symbol}</span>}
                </h3>
            </div>

            <div className={styles.chatContainer} style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border)' }}>
                <div className={styles.chatMessages}>
                    {messages.length === 0 && (
                        <div className={styles.emptyState}>
                            <MessageSquare size={48} />
                            <h3 style={{ color: 'var(--text-1)', fontSize: 18, fontWeight: 700 }}>AI 投資研究助手</h3>
                            <p style={{ maxWidth: 400 }}>
                                輸入股票代號或問題，AI 會透過 Google 搜尋最新資訊後回答。<br /><br />
                                💡 試試看：<br />
                                「分析台積電 2330 近期走勢」<br />
                                「NVDA 最新財報表現如何？」<br />
                                「Fed 最新利率決策影響」
                            </p>
                        </div>
                    )}

                    {messages.map(msg => (
                        <div key={msg.id}>
                            <div className={`${styles.chatBubble} ${msg.role === 'user' ? styles.chatUser : styles.chatAi}`}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, fontSize: 11, opacity: 0.7 }}>
                                    {msg.role === 'user' ? <User size={12} /> : <Bot size={12} />}
                                    {msg.role === 'user' ? '你' : 'AI 助手'}
                                </div>
                                {msg.content}
                            </div>
                            {/* Grounding Sources */}
                            {msg.sources && msg.sources.length > 0 && (
                                <div style={{ maxWidth: '80%', padding: '6px 12px', fontSize: 11, color: 'var(--text-3)' }}>
                                    📎 參考來源：
                                    {msg.sources.map((s, i) => (
                                        <a key={i} href={s.uri} target="_blank" rel="noopener noreferrer"
                                            style={{ display: 'inline-flex', alignItems: 'center', gap: 3, marginLeft: 6, color: 'var(--accent)', textDecoration: 'none' }}>
                                            {s.title || '來源'} <ExternalLink size={10} />
                                        </a>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))}

                    {loading && (
                        <div className={`${styles.chatBubble} ${styles.chatAi}`} style={{ opacity: 0.6 }}>
                            <Loader2 size={16} className={styles.spinning} style={{ display: 'inline', marginRight: 8 }} />
                            正在搜尋最新資訊...
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                <div className={styles.chatInput}>
                    <input
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="輸入股票代號或投資問題..."
                        disabled={loading}
                    />
                    <button className={styles.runBtn} onClick={sendMessage} disabled={loading || !input.trim()} style={{ borderRadius: 24, padding: '12px 20px' }}>
                        {loading ? <Loader2 size={16} className={styles.spinning} /> : <Send size={16} />}
                    </button>
                </div>
            </div>
        </div>
    );
}
