"""
SMC/ICT Service - Smart Money Concepts 技術分析
提供 BOS/CHoCH/OB/FVG/Liquidity 計算
"""
from typing import List, Dict, Optional
import os
import time
import copy
import threading
from collections import OrderedDict

_SMC_CACHE_TTL_SEC = max(30, int((os.environ.get("SMC_CACHE_TTL_SEC") or "300").strip() or 300))
_SMC_CACHE_MAXSIZE = max(32, int((os.environ.get("SMC_CACHE_MAXSIZE") or "256").strip() or 256))
_smc_cache: "OrderedDict[str, Dict]" = OrderedDict()
_smc_cache_lock = threading.Lock()


class SMCService:
    """SMC/ICT 技術分析服務"""
    
    # 結構類型
    STRUCTURE_TYPES = {
        "BOS": "Break of Structure",  # 結構突破
        "CHOCH": "Change of Character",  # 趨勢反轉
        "HH": "Higher High",
        "HL": "Higher Low",
        "LH": "Lower High",
        "LL": "Lower Low",
    }
    
    def __init__(self, swing_lookback: int = 5):
        """
        Args:
            swing_lookback: 判斷 swing high/low 的回看期間
        """
        self.swing_lookback = swing_lookback

    def _cache_key(self, history: List[Dict]) -> str:
        if not history:
            return f"empty:{self.swing_lookback}"
        first = history[0] if isinstance(history[0], dict) else {}
        last = history[-1] if isinstance(history[-1], dict) else {}
        return "|".join(
            [
                str(self.swing_lookback),
                str(len(history)),
                str(first.get("date") or first.get("time") or ""),
                str(last.get("date") or last.get("time") or ""),
                str(last.get("open") or ""),
                str(last.get("high") or ""),
                str(last.get("low") or ""),
                str(last.get("close") or ""),
            ]
        )

    def _read_cache(self, key: str) -> Optional[Dict]:
        now = time.time()
        with _smc_cache_lock:
            row = _smc_cache.get(key)
            if not isinstance(row, dict):
                return None
            ts = float(row.get("ts") or 0.0)
            payload = row.get("payload")
            if ts <= 0 or (now - ts) > _SMC_CACHE_TTL_SEC:
                _smc_cache.pop(key, None)
                return None
            if not isinstance(payload, dict):
                return None
            _smc_cache.move_to_end(key)
            return copy.deepcopy(payload)

    def _write_cache(self, key: str, payload: Dict) -> None:
        with _smc_cache_lock:
            _smc_cache[key] = {"ts": time.time(), "payload": copy.deepcopy(payload)}
            _smc_cache.move_to_end(key)
            while len(_smc_cache) > _SMC_CACHE_MAXSIZE:
                _smc_cache.popitem(last=False)
    
    def analyze(self, history: List[Dict]) -> Dict:
        """
        完整 SMC 分析
        
        Returns:
            {
                "swings": [...],        # Swing highs/lows
                "structures": [...],    # BOS/CHoCH
                "order_blocks": [...],  # OB
                "fvg": [...],           # Fair Value Gaps
                "liquidity": [...],     # Liquidity levels
                "trend": "bullish/bearish/neutral"
            }
        """
        cache_key = self._cache_key(history)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        if len(history) < self.swing_lookback * 2:
            return {"error": "資料不足"}
        
        # 識別 Swing 點
        swings = self._identify_swings(history)
        
        # 識別結構（BOS/CHoCH）
        structures = self._identify_structures(swings, history)
        
        # 識別 Order Blocks
        order_blocks = self._identify_order_blocks(history, structures)
        
        # 識別 Fair Value Gaps
        fvg = self._identify_fvg(history)
        
        # 識別 Liquidity
        liquidity = self._identify_liquidity(history, swings)
        
        # 判斷趨勢
        trend = self._determine_trend(swings)
        
        payload = {
            "swings": swings,
            "structures": structures,
            "order_blocks": order_blocks,
            "fvg": fvg,
            "liquidity": liquidity,
            "trend": trend
        }
        self._write_cache(cache_key, payload)
        return copy.deepcopy(payload)
    
    def _identify_swings(self, history: List[Dict]) -> List[Dict]:
        """識別 Swing High 和 Swing Low"""
        swings = []
        lookback = self.swing_lookback
        
        for i in range(lookback, len(history) - lookback):
            current = history[i]
            
            # 取得前後蠟燭
            before = history[i-lookback:i]
            after = history[i+1:i+lookback+1]
            
            current_high = current.get("high", 0)
            current_low = current.get("low", 0)
            
            # 檢查是否為 Swing High
            is_swing_high = all(
                current_high > h.get("high", 0) for h in before
            ) and all(
                current_high > h.get("high", 0) for h in after
            )
            
            # 檢查是否為 Swing Low
            is_swing_low = all(
                current_low < h.get("low", float("inf")) for h in before
            ) and all(
                current_low < h.get("low", float("inf")) for h in after
            )
            
            if is_swing_high:
                swings.append({
                    "index": i,
                    "date": current.get("date"),
                    "type": "high",
                    "price": current_high
                })
            
            if is_swing_low:
                swings.append({
                    "index": i,
                    "date": current.get("date"),
                    "type": "low",
                    "price": current_low
                })
        
        return sorted(swings, key=lambda x: x["index"])
    
    def _identify_structures(
        self, 
        swings: List[Dict], 
        history: List[Dict]
    ) -> List[Dict]:
        """識別 BOS 和 CHoCH"""
        structures = []
        
        if len(swings) < 4:
            return structures
        
        # 追蹤最近的 swing points
        prev_high = None
        prev_low = None
        trend = "neutral"
        
        for swing in swings:
            if swing["type"] == "high":
                if prev_high is not None:
                    if swing["price"] > prev_high["price"]:
                        # Higher High
                        if trend == "bearish":
                            # CHoCH - 趨勢反轉
                            structures.append({
                                "type": "CHOCH",
                                "direction": "bullish",
                                "from_index": prev_high["index"],
                                "to_index": swing["index"],
                                "from_date": prev_high["date"],
                                "to_date": swing["date"],
                                "price": prev_high["price"],
                                "description": "看跌反轉為看漲"
                            })
                            trend = "bullish"
                        else:
                            trend = "bullish"
                    else:
                        # Lower High
                        if trend == "bullish":
                            # 可能的趨勢轉變預警
                            pass
                prev_high = swing
            
            elif swing["type"] == "low":
                if prev_low is not None:
                    if prev_high is not None and swing["price"] < prev_low["price"]:
                        # Lower Low
                        if trend == "bullish":
                            # BOS - 結構突破
                            structures.append({
                                "type": "BOS",
                                "direction": "bearish",
                                "from_index": prev_low["index"],
                                "to_index": swing["index"],
                                "from_date": prev_low["date"],
                                "to_date": swing["date"],
                                "price": prev_low["price"],
                                "description": "跌破前低，看跌結構"
                            })
                            trend = "bearish"
                        else:
                            trend = "bearish"
                    elif swing["price"] > prev_low["price"]:
                        # Higher Low
                        if trend == "bearish":
                            # CHoCH
                            structures.append({
                                "type": "CHOCH",
                                "direction": "bullish",
                                "from_index": prev_low["index"],
                                "to_index": swing["index"],
                                "from_date": prev_low["date"],
                                "to_date": swing["date"],
                                "price": prev_low["price"],
                                "description": "看跌反轉為看漲"
                            })
                            trend = "bullish"
                prev_low = swing
        
        return structures
    
    def _identify_order_blocks(
        self, 
        history: List[Dict],
        structures: List[Dict]
    ) -> List[Dict]:
        """識別 Order Blocks（供需區）"""
        order_blocks = []
        
        for structure in structures:
            idx = structure.get("from_index", 0)
            if idx < 1 or idx >= len(history):
                continue
            
            # Order Block 通常在結構突破前的最後一根反向蠟燭
            candle = history[idx - 1]
            
            is_bullish_ob = structure["direction"] == "bullish"
            
            # 確認是反向蠟燭
            candle_open = candle.get("open", 0)
            candle_close = candle.get("close", 0)
            is_bearish_candle = candle_close < candle_open
            is_bullish_candle = candle_close > candle_open
            
            if is_bullish_ob and is_bearish_candle:
                order_blocks.append({
                    "type": "bullish_ob",
                    "index": idx - 1,
                    "date": candle.get("date"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "mitigated": False,
                    "description": "看漲 Order Block（需求區）"
                })
            elif not is_bullish_ob and is_bullish_candle:
                order_blocks.append({
                    "type": "bearish_ob",
                    "index": idx - 1,
                    "date": candle.get("date"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "mitigated": False,
                    "description": "看跌 Order Block（供給區）"
                })
        
        # 檢查 OB 是否已被 mitigate
        for ob in order_blocks:
            ob_idx = ob["index"]
            for i in range(ob_idx + 1, len(history)):
                if ob["type"] == "bullish_ob":
                    # 看漲 OB 被向下穿透 = mitigated
                    if history[i].get("low", 0) < ob["low"]:
                        ob["mitigated"] = True
                        ob["mitigated_at"] = history[i].get("date")
                        break
                else:
                    # 看跌 OB 被向上穿透 = mitigated
                    if history[i].get("high", 0) > ob["high"]:
                        ob["mitigated"] = True
                        ob["mitigated_at"] = history[i].get("date")
                        break
        
        return order_blocks
    
    def _identify_fvg(self, history: List[Dict]) -> List[Dict]:
        """識別 Fair Value Gaps（公平價值缺口）"""
        fvg_list = []
        
        for i in range(2, len(history)):
            candle_1 = history[i - 2]
            candle_2 = history[i - 1]
            candle_3 = history[i]
            
            # 看漲 FVG：第三根 K 的低點 > 第一根 K 的高點
            if candle_3.get("low", 0) > candle_1.get("high", 0):
                fvg_list.append({
                    "type": "bullish_fvg",
                    "index": i - 1,  # 中間的蠟燭
                    "date": candle_2.get("date"),
                    "top": candle_3.get("low"),
                    "bottom": candle_1.get("high"),
                    "filled": False,
                    "description": "看漲 FVG"
                })
            
            # 看跌 FVG：第三根 K 的高點 < 第一根 K 的低點
            elif candle_3.get("high", 0) < candle_1.get("low", float("inf")):
                fvg_list.append({
                    "type": "bearish_fvg",
                    "index": i - 1,
                    "date": candle_2.get("date"),
                    "top": candle_1.get("low"),
                    "bottom": candle_3.get("high"),
                    "filled": False,
                    "description": "看跌 FVG"
                })
        
        # 檢查 FVG 是否已填補
        for fvg in fvg_list:
            fvg_idx = fvg["index"]
            for i in range(fvg_idx + 1, len(history)):
                if fvg["type"] == "bullish_fvg":
                    # 看漲 FVG 被向下回測 = filled
                    if history[i].get("low", float("inf")) <= fvg["top"]:
                        fvg["filled"] = True
                        fvg["filled_at"] = history[i].get("date")
                        break
                else:
                    # 看跌 FVG 被向上回測 = filled
                    if history[i].get("high", 0) >= fvg["bottom"]:
                        fvg["filled"] = True
                        fvg["filled_at"] = history[i].get("date")
                        break
        
        return fvg_list
    
    def _identify_liquidity(
        self, 
        history: List[Dict], 
        swings: List[Dict]
    ) -> List[Dict]:
        """識別流動性區域（等高/等低點群）"""
        liquidity = []
        
        # 分組 swing highs 和 lows
        highs = [s for s in swings if s["type"] == "high"]
        lows = [s for s in swings if s["type"] == "low"]
        
        # 檢查相近的高點（流動性池）
        tolerance = 0.01  # 1% 容差
        
        for i, h1 in enumerate(highs):
            cluster = [h1]
            for h2 in highs[i+1:]:
                if abs(h1["price"] - h2["price"]) / h1["price"] < tolerance:
                    cluster.append(h2)
            
            if len(cluster) >= 2:
                avg_price = sum(h["price"] for h in cluster) / len(cluster)
                liquidity.append({
                    "type": "buy_side_liquidity",
                    "price": avg_price,
                    "count": len(cluster),
                    "dates": [h["date"] for h in cluster],
                    "swept": False,
                    "description": f"{len(cluster)} 個等高點，買方流動性"
                })
        
        for i, low1 in enumerate(lows):
            cluster = [low1]
            for low2 in lows[i+1:]:
                if abs(low1["price"] - low2["price"]) / low1["price"] < tolerance:
                    cluster.append(low2)
            
            if len(cluster) >= 2:
                avg_price = sum(low_s["price"] for low_s in cluster) / len(cluster)
                liquidity.append({
                    "type": "sell_side_liquidity",
                    "price": avg_price,
                    "count": len(cluster),
                    "dates": [low_s["date"] for low_s in cluster],
                    "swept": False,
                    "description": f"{len(cluster)} 個等低點，賣方流動性"
                })
        
        return liquidity
    
    def _determine_trend(self, swings: List[Dict]) -> str:
        """判斷當前趨勢"""
        if len(swings) < 4:
            return "neutral"
        
        # 取最近 4 個 swing
        recent = swings[-4:]
        
        highs = [s for s in recent if s["type"] == "high"]
        lows = [s for s in recent if s["type"] == "low"]
        
        if len(highs) >= 2 and len(lows) >= 2:
            # HH + HL = bullish
            if highs[-1]["price"] > highs[-2]["price"] and lows[-1]["price"] > lows[-2]["price"]:
                return "bullish"
            # LH + LL = bearish
            elif highs[-1]["price"] < highs[-2]["price"] and lows[-1]["price"] < lows[-2]["price"]:
                return "bearish"
        
        return "neutral"
    
    def get_chart_markers(self, analysis: Dict) -> List[Dict]:
        """
        將分析結果轉換為圖表標記
        用於 Lightweight Charts
        """
        markers = []
        
        # Swing 點
        for swing in analysis.get("swings", []):
            markers.append({
                "time": swing["date"],
                "position": "aboveBar" if swing["type"] == "high" else "belowBar",
                "color": "#26a69a" if swing["type"] == "high" else "#ef5350",
                "shape": "arrowDown" if swing["type"] == "high" else "arrowUp",
                "text": "SH" if swing["type"] == "high" else "SL",
                "size": 1
            })
        
        # BOS/CHoCH 結構
        for struct in analysis.get("structures", []):
            color = "#26a69a" if struct["direction"] == "bullish" else "#ef5350"
            markers.append({
                "time": struct["to_date"],
                "position": "aboveBar" if struct["direction"] == "bullish" else "belowBar",
                "color": color,
                "shape": "circle",
                "text": struct["type"],
                "size": 2
            })
        
        return markers
    
    def get_chart_rectangles(self, analysis: Dict) -> List[Dict]:
        """
        取得矩形區塊（OB/FVG）
        用於 Lightweight Charts 繪製
        """
        rectangles = []
        
        # Order Blocks
        for ob in analysis.get("order_blocks", []):
            if ob["mitigated"]:
                continue  # 跳過已被 mitigate 的 OB
            
            color = "rgba(38, 166, 154, 0.2)" if ob["type"] == "bullish_ob" else "rgba(239, 83, 80, 0.2)"
            border = "#26a69a" if ob["type"] == "bullish_ob" else "#ef5350"
            
            rectangles.append({
                "type": "order_block",
                "start_date": ob["date"],
                "top": ob["high"],
                "bottom": ob["low"],
                "color": color,
                "border_color": border,
                "label": "Bullish OB" if ob["type"] == "bullish_ob" else "Bearish OB"
            })
        
        # FVG
        for fvg in analysis.get("fvg", []):
            if fvg["filled"]:
                continue
            
            color = "rgba(103, 58, 183, 0.2)" if fvg["type"] == "bullish_fvg" else "rgba(255, 152, 0, 0.2)"
            border = "#673ab7" if fvg["type"] == "bullish_fvg" else "#ff9800"
            
            rectangles.append({
                "type": "fvg",
                "start_date": fvg["date"],
                "top": fvg["top"],
                "bottom": fvg["bottom"],
                "color": color,
                "border_color": border,
                "label": "Bullish FVG" if fvg["type"] == "bullish_fvg" else "Bearish FVG"
            })
        
        return rectangles


# 單例
smc_service = SMCService()
