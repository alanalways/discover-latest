"""
Dexter Panel 元件 — 執行面板 HTML 生成
可摺疊設計，顯示：任務規劃 → 執行進度 → 驗證結果 → 綜合分析 → 執行摘要
"""
import html
from typing import Dict, List, Optional


def create_dexter_panel_html(execution_log: Dict, lang: str = "zh-TW") -> str:
    """
    生成 Dexter 執行面板 HTML

    execution_log 結構:
    {
        "query": str,
        "tasks": [{"name": str, "tool": str, "status": "completed"|"executing"|"pending"|"failed", "duration": float}],
        "validation": [{"label": str, "passed": bool}],
        "analysis": str,  # Gemini 綜合分析文字
        "summary": {"duration": float, "api_calls": int, "confidence": int},
        "error": str | None,
    }
    """
    if not execution_log:
        return ""

    error = execution_log.get("error")
    if error:
        return f'''
        <div class="dexter-panel">
            <div class="dexter-header">
                <span class="dexter-icon"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2M20 14h2M15 13v2M9 13v2"/></svg></span>
                <span>Dexter 深度分析</span>
            </div>
            <div class="dexter-body" style="display:block;">
                <p style="color:var(--danger);font-size:13px;">{html.escape(str(error))}</p>
            </div>
        </div>'''

    query = html.escape(execution_log.get("query", ""))
    tasks = execution_log.get("tasks", [])
    validation = execution_log.get("validation", [])
    analysis = execution_log.get("analysis", "")
    summary = execution_log.get("summary", {})

    # 任務列表
    tasks_html = ""
    for task in tasks:
        status = task.get("status", "pending")
        duration = task.get("duration", 0)
        tool = task.get("tool", "")
        name = html.escape(task.get("name", ""))

        if status == "completed":
            icon = "&#10003;"
            cls = "completed"
            time_str = f" — {duration:.1f}s"
        elif status == "executing":
            icon = "&#9203;"
            cls = "executing"
            time_str = " — 執行中"
        elif status == "failed":
            icon = "&#10007;"
            cls = "failed"
            time_str = " — 失敗"
        else:
            icon = "&#9208;"
            cls = "pending"
            time_str = " — 等待中"

        tasks_html += f'<div class="task-item {cls}">{icon} {name} ({tool}){time_str}</div>\n'

    # 驗證結果
    validation_html = ""
    for v in validation:
        label = html.escape(v.get("label", ""))
        passed = v.get("passed", False)
        cls = "pass" if passed else "fail"
        icon = "&#10003;" if passed else "&#10007;"
        validation_html += f'<div class="validation-item {cls}">{label}: {icon}</div>\n'

    # 分析內容
    analysis_html = ""
    if analysis:
        safe_analysis = html.escape(analysis)
        analysis_html = f'''
        <div class="dexter-phase">
            <div class="phase-title">綜合分析</div>
            <div style="white-space:pre-wrap;color:var(--text-2);font-size:13px;line-height:1.7;">{safe_analysis}</div>
        </div>'''

    # 執行摘要
    summary_html = ""
    if summary:
        dur = summary.get("duration", 0)
        api_calls = summary.get("api_calls", 0)
        confidence = summary.get("confidence", 0)
        summary_html = f'''
        <div class="dexter-summary">
            <span>耗時: {dur:.1f}s</span>
            <span>API 呼叫: {api_calls} 次</span>
            <span>置信度: {confidence}%</span>
        </div>'''

    panel_id = "dexter-panel-main"

    return f'''
    <div class="dexter-panel" id="{panel_id}">
        <div class="dexter-header" onclick="(function(){{var b=document.getElementById('{panel_id}');if(b)b.classList.toggle('collapsed');}})()">
            <span class="dexter-icon"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2M20 14h2M15 13v2M9 13v2"/></svg></span>
            <span>Dexter 深度分析</span>
            <span style="margin-left:auto;font-size:11px;color:var(--text-3);">{query}</span>
            <span class="dexter-toggle">&#9660;</span>
        </div>
        <div class="dexter-body">
            <div class="dexter-phase">
                <div class="phase-title">任務規劃</div>
                <div class="task-list">{tasks_html}</div>
            </div>

            {f'<div class="dexter-phase"><div class="phase-title">數據驗證</div><div class="validation-list">{validation_html}</div></div>' if validation_html else ''}

            {analysis_html}
            {summary_html}
        </div>
    </div>'''
