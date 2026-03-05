'use client';

import { useState, useRef, useEffect } from 'react';
import { MessageSquare, Send, Loader2, Bot, User } from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import styles from '../shared.module.css';

interface Message {
    id: string;
    role: 'user' | 'ai';
    content: string;
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
        setInput('');
        setLoading(true);

        try {
            // Extract symbol from context
            const symMatch = input.match(/(\d{4}|[A-Z]{1,5})/);
            const detectedSymbol = symMatch ? symMatch[1] : symbol;
            if (detectedSymbol && !symbol) setSymbol(detectedSymbol);

            const res = await api.fetch<{ query: string; analysis: string; error: string | null }>('/api/dexter/execute', {
                method: 'POST',
                body: JSON.stringify({
                    symbol: detectedSymbol || '',
                    query: input.trim(),
                }),
            });

            const aiText = res.analysis || res.error || 'AI 無法回應，請稍後重試。';
            const aiMsg: Message = { id: (Date.now() + 1).toString(), role: 'ai', content: aiText, timestamp: new Date() };
            setMessages(prev => [...prev, aiMsg]);
        } catch (err: unknown) {
            const errorMsg = err instanceof Error ? err.message : 'AI 回應失敗';
            setMessages(prev => [...prev, { id: (Date.now() + 1).toString(), role: 'ai', content: `❌ ${errorMsg}`, timestamp: new Date() }]);
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
                    <Bot size={18} /> Dexter AI 研究助手
                    {symbol && <span style={{ fontSize: 12, color: 'var(--accent)', marginLeft: 8 }}>分析中: {symbol}</span>}
                </h3>
            </div>

            <div className={styles.chatContainer} style={{ background: 'var(--bg-surface)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border)' }}>
                <div className={styles.chatMessages}>
                    {messages.length === 0 && (
                        <div className={styles.emptyState}>
                            <MessageSquare size={48} />
                            <h3 style={{ color: 'var(--text-1)', fontSize: 18, fontWeight: 700 }}>與 Dexter 對話</h3>
                            <p style={{ maxWidth: 400 }}>
                                輸入股票代號或問題開始研究。例如：<br />
                                「分析台積電 2330」<br />
                                「NVDA 近期有什麼利多？」<br />
                                「比較台積電和聯電」
                            </p>
                        </div>
                    )}

                    {messages.map(msg => (
                        <div key={msg.id} className={`${styles.chatBubble} ${msg.role === 'user' ? styles.chatUser : styles.chatAi}`}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, fontSize: 11, opacity: 0.7 }}>
                                {msg.role === 'user' ? <User size={12} /> : <Bot size={12} />}
                                {msg.role === 'user' ? '你' : 'Dexter'}
                            </div>
                            {msg.content}
                        </div>
                    ))}

                    {loading && (
                        <div className={`${styles.chatBubble} ${styles.chatAi}`} style={{ opacity: 0.6 }}>
                            <Loader2 size={16} className={styles.spinning} style={{ display: 'inline', marginRight: 8 }} />
                            Dexter 正在研究中...
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                <div className={styles.chatInput}>
                    <input
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="輸入股票代號或問題..."
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
