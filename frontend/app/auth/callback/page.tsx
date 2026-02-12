"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import api from "@/lib/api";

interface AuthDiagnoseData {
    supabase_project_ref?: string;
    supabase_host?: string;
    callback_default?: string;
    space_url?: string;
    checks?: {
        supabase_url_present?: boolean;
        supabase_host_valid?: boolean;
        space_url_present?: boolean;
        anon_key_present?: boolean;
        google_client_id_present_in_env?: boolean;
        google_client_id_present_in_vault?: boolean;
    };
}

function AuthCallbackContent() {
    const searchParams = useSearchParams();
    const [message, setMessage] = useState("正在處理登入...");
    const [diagnose, setDiagnose] = useState<AuthDiagnoseData | null>(null);

    useEffect(() => {
        const code = searchParams.get("code");
        const queryToken = searchParams.get("access_token");
        const queryError = searchParams.get("error_description") || searchParams.get("error");
        const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
        const hashToken = hashParams.get("access_token");
        const tokenFromCallback = queryToken || hashToken;

        const loadDiagnose = async () => {
            try {
                const res = await fetch("/api/auth/diagnose", { cache: "no-store" });
                if (!res.ok) return;
                const data = await res.json();
                setDiagnose(data as AuthDiagnoseData);
            } catch {
                // ignore
            }
        };

        const handleOAuthError = async (rawError: string) => {
            const decoded = decodeURIComponent(rawError);
            const lower = decoded.toLowerCase();

            if (lower.includes("unable to exchange external code")) {
                setMessage("登入失敗：Google OAuth 交換失敗，請檢查 Supabase/Google OAuth 設定。");
                await loadDiagnose();
                return;
            }

            if (
                lower.includes("blocked") ||
                lower.includes("org_internal") ||
                lower.includes("organization") ||
                lower.includes("access_blocked")
            ) {
                setMessage(
                    "登入被 Google 機構政策阻擋。請改用個人 Gmail，或在手機外部瀏覽器（Safari/Chrome）重新嘗試。"
                );
                await loadDiagnose();
                return;
            }

            setMessage(`登入失敗：${decoded}`);
        };

        const finishLogin = async () => {
            try {
                if (queryError) {
                    await handleOAuthError(queryError);
                    return;
                }

                if (tokenFromCallback) {
                    api.setToken(tokenFromCallback);
                    await api.getCurrentUser();
                    setMessage("登入成功，正在返回首頁...");
                    window.location.href = "/";
                    return;
                }

                if (!code) {
                    throw new Error("缺少授權碼，請重新登入");
                }

                const res = await api.loginWithGoogleCode(code);
                if (!res.success || !res.access_token) {
                    throw new Error(res.message || "OAuth 交換失敗");
                }
                api.setToken(res.access_token);
                setMessage("登入成功，正在返回首頁...");
                window.location.href = "/";
            } catch (err) {
                console.error("OAuth callback failed:", err);
                setMessage("登入失敗：請重新嘗試，或稍後再試。");
            }
        };

        void finishLogin();
    }, [searchParams]);

    return (
        <div
            style={{
                minHeight: "60vh",
                display: "grid",
                placeItems: "center",
                color: "var(--text-1)",
            }}
        >
            <div
                style={{
                    padding: "24px 28px",
                    border: "1px solid var(--border)",
                    borderRadius: "12px",
                    background: "var(--bg-card)",
                    fontSize: 14,
                    maxWidth: 860,
                    width: "min(92vw, 860px)",
                }}
            >
                {message}
                {diagnose && (
                    <div
                        style={{
                            marginTop: 14,
                            paddingTop: 12,
                            borderTop: "1px solid var(--border)",
                            fontSize: 12,
                            lineHeight: 1.6,
                            color: "var(--text-2)",
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-all",
                        }}
                    >
                        {`診斷資訊：
Supabase Project Ref: ${diagnose.supabase_project_ref || "（缺少）"}
Supabase Host: ${diagnose.supabase_host || "（缺少）"}
Callback URL: ${diagnose.callback_default || "（缺少）"}
SPACE_URL: ${diagnose.space_url || "（缺少）"}

檢查：
- SUPABASE_URL: ${diagnose.checks?.supabase_url_present ? "OK" : "缺少"}
- SUPABASE Host 格式: ${diagnose.checks?.supabase_host_valid ? "OK" : "異常"}
- SPACE_URL: ${diagnose.checks?.space_url_present ? "OK" : "缺少"}
- SUPABASE_ANON_KEY: ${diagnose.checks?.anon_key_present ? "OK" : "缺少"}
- ENV GOOGLE_CLIENT_ID: ${diagnose.checks?.google_client_id_present_in_env ? "OK" : "缺少"}
- Vault GOOGLE_CLIENT_ID: ${diagnose.checks?.google_client_id_present_in_vault ? "OK" : "缺少"}`}
                    </div>
                )}
            </div>
        </div>
    );
}

export default function AuthCallbackPage() {
    return (
        <Suspense
            fallback={
                <div
                    style={{
                        minHeight: "60vh",
                        display: "grid",
                        placeItems: "center",
                        color: "var(--text-1)",
                    }}
                >
                    正在處理登入...
                </div>
            }
        >
            <AuthCallbackContent />
        </Suspense>
    );
}

