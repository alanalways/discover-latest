"""
股票比較頁面
允許使用者輸入多檔股票代號，比較其歷史走勢 (Normalized %) 與基本面數據
"""
import logging
from typing import List, Dict
import json
from datetime import datetime, timedelta
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from components.chart_viewer import create_line_chart
from adapters.finmind_adapter import finmind_adapter
from components.i18n import t


logger = logging.getLogger(__name__)
def _fetch_history_data(symbol: str, days: int = 365) -> List[Dict]:
    """取得歷史資料 (簡化版，無快取，直接調用 Adapter)"""
    # 1. 嘗試 FinMind (台股)
    if symbol.isdigit() and len(symbol) >= 4:
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            data = finmind_adapter.get_tw_stock_price_sync(symbol, start, end)
            if data:
                # 轉為標準格式
                return [{"date": d["date"], "close": d["close"]} for d in data]
        except Exception as e:
            logger.debug(f"[Compare] FinMind {symbol} fail: {e}")

    # 2. 嘗試 FinMind USStockPrice (美股)
    try:
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        data = finmind_adapter.get_us_stock_price_sync(symbol, start, end)
        if data:
            return [{"date": d["date"], "close": d["close"]} for d in data]
    except Exception as e:
        logger.debug(f"[Compare] FinMind US {symbol} fail: {e}")
    
    return []

def _fetch_fundamentals_batch(symbols: List[str]) -> Dict[str, Dict]:
    """批次取得基本面資料"""
    # 這裡簡化，僅使用 FinMind 或 yfinance info
    results = {}
    
    def _get_one(sym):
        info = {}
        # FinMind
        if sym.isdigit() and len(sym) >= 4:
            try:
                per_pbr = finmind_adapter.get_tw_stock_per_pbr_sync(sym)
                if per_pbr:
                    info.update({"pe": per_pbr.get("PER", 0), "pb": per_pbr.get("PBR", 0), "yield": per_pbr.get("yield", 0)})
                # Name
                basic = finmind_adapter.get_tw_stock_info_sync(sym)
                if basic:
                    info["name"] = basic[0].get("name", sym)
            except:
                pass
        
    # 美股用 FinMind 取得基本面
        if not info.get("pe"):
            try:
                end = datetime.now().strftime("%Y-%m-%d")
                start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                us_data = finmind_adapter.get_us_stock_price_sync(sym, start, end)
                if us_data:
                    info["name"] = info.get("name") or sym
                    last = us_data[-1]
                    info["price"] = last.get("close", 0)
            except:
                pass
        return sym, info

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_get_one, s) for s in symbols]
        for f in futures:
            try:
                s, i = f.result()
                results[s] = i
            except:
                pass
    return results

def create_compare_page(
    symbols: List[str] = None,
    lang: str = "zh-TW",
) -> str:
    """建立比較頁面"""
    if not symbols:
        symbols = ["2330"] # Default

    # 1. UI: Search Bar for adding symbols
    # 我們需要一個介面來輸入代號，並更新頁面
    # 這裡使用簡單的輸入框 + JS
    
    input_section = f'''
    <div style="background:rgba(255,255,255,0.03);padding:20px;border-radius:12px;margin-bottom:24px;">
        <h2 style="margin-top:0;font-size:20px;color:var(--text-1);">📈 股票績效比較</h2>
        <div style="display:flex;gap:12px;margin-top:16px;">
            <input type="text" id="compare-input" class="watchlist-add-input" 
                   value="{','.join(symbols)}" 
                   placeholder="輸入代號，以逗號分隔 (例如: 2330, 2317, AAPL)" />
            <button class="watchlist-add-btn" onclick="updateCompare()">
                更新比較
            </button>
        </div>
        <p style="font-size:12px;color:var(--text-3);margin-top:8px;">
            * 最多比較 4 檔，自動正規化以第一筆資料為基準 (0%)
        </p>
    </div>
    
    <script>
    function updateCompare() {{
        var val = document.getElementById('compare-input').value;
        if(!val) return;
        var syms = val.split(',').map(s=>s.trim()).filter(s=>s);
        // Dispatch action
        var payload = JSON.stringify({{ action: "compare_update", symbols: syms }});
        dispatchAction(payload);
    }}
    </script>
    '''

    # 2. Fetch Data & Prepare Chart
    datasets = []
    colors = ["#22C55E", "#3B82F6", "#D4A76A", "#F43F5E"]
    
    # Fundamental Info
    fundamentals = _fetch_fundamentals_batch(symbols)
    
    for i, sym in enumerate(symbols[:4]): # Limit to 4
        hist = _fetch_history_data(sym)
        if not hist:
            continue
            
        # Normalize
        base_price = hist[0]["close"]
        norm_data = []
        for h in hist:
            pct = ((h["close"] - base_price) / base_price) * 100 if base_price else 0
            norm_data.append({"date": h["date"], "value": pct})
            
        info = fundamentals.get(sym, {})
        name = info.get("name", sym)
        
        datasets.append({
            "symbol": sym,
            "name": name,
            "color": colors[i % len(colors)],
            "data": norm_data
        })

    chart_html = create_line_chart(datasets, height=450)
    
    # 3. Fundamental Table
    table_rows = ""
    for ds in datasets:
        sym = ds["symbol"]
        info = fundamentals.get(sym, {})
        c = ds["color"]
        
        pe = info.get("pe", 0)
        pb = info.get("pb", 0)
        dy = info.get("yield", 0)
        mcap = info.get("market_cap", 0)
        if mcap > 100000000:
            mcap_str = f"{mcap/100000000:.1f}億"
        else:
            mcap_str = f"{mcap}"
            
        table_rows += f'''
        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
            <td style="padding:12px;"><span style="color:{c};font-weight:bold;">●</span> {sym}</td>
            <td style="padding:12px;color:var(--text-2);">{info.get("name", "--")}</td>
            <td style="padding:12px;text-align:right;">{pe:.2f}</td>
            <td style="padding:12px;text-align:right;">{pb:.2f}</td>
            <td style="padding:12px;text-align:right;">{dy:.2f}%</td>
            <td style="padding:12px;text-align:right;">{mcap_str}</td>
        </tr>
        '''
        
    table_html = f'''
    <div style="background:rgba(255,255,255,0.03);border-radius:12px;overflow:hidden;margin-top:24px;">
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <thead>
                <tr style="background:rgba(255,255,255,0.05);color:var(--text-3);text-align:left;">
                    <th style="padding:12px;">Code</th>
                    <th style="padding:12px;">Name</th>
                    <th style="padding:12px;text-align:right;">P/E</th>
                    <th style="padding:12px;text-align:right;">P/B</th>
                    <th style="padding:12px;text-align:right;">Yield</th>
                    <th style="padding:12px;text-align:right;">Mkt Cap</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>
    '''

    return f'''
    <div class="compare-page">
        {input_section}
        {chart_html}
        {table_html}
    </div>
    '''
