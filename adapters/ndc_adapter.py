
import logging
import requests
import json
import time
from datetime import datetime
from typing import List, Dict, Optional


logger = logging.getLogger(__name__)
class NDCAdapter:
    """國發會資料 Adapter (National Development Council)"""
    
    LIGHTSCORE_URL = 'https://index.ndc.gov.tw/n/json/lightscore'

    def __init__(self):
        self._cache: List[Dict] = []
        self._cache_ts: float = 0.0
        self._ttl_seconds = 6 * 3600  # 6 小時

    def get_business_cycle_score(self) -> List[Dict]:
        """
        取得台灣景氣對策信號分數
        回傳欄位: date (YYYYMM), score, light (藍/黃藍/綠/黃紅/紅)
        """
        now = time.time()
        if self._cache and (now - self._cache_ts) < self._ttl_seconds:
            return self._cache

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://index.ndc.gov.tw/",
            "Origin": "https://index.ndc.gov.tw",
        }
        try:
            res = requests.get(self.LIGHTSCORE_URL, headers=headers, timeout=12)
            res.raise_for_status()
            data = json.loads(res.text)
            
            # data['line'] 格式範例: [{'x': '202404', 'y': 35}, ...]
            raw_list = data.get('line', [])
            
            result = []
            for item in raw_list:
                date_str = item.get('x', '')
                score = float(item.get('y', 0))
                
                # 判斷燈號
                light = "N/A"
                if score >= 38:
                    light = "Red"       # 紅燈
                elif 32 <= score <= 37:
                    light = "YellowRed" # 黃紅燈
                elif 23 <= score <= 31:
                    light = "Green"     # 綠燈
                elif 17 <= score <= 22:
                    light = "YellowBlue"# 黃藍燈
                elif score <= 16:
                    light = "Blue"      # 藍燈
                    
                result.append({
                    "date": date_str,
                    "score": score,
                    "light": light
                })
                
            # 排序：舊 -> 新
            result.sort(key=lambda x: x['date'])
            if result:
                self._cache = result
                self._cache_ts = now
            return result
            
        except Exception as e:
            logger.debug(f"[NDC] 取得景氣燈號失敗: {e}")
            if self._cache:
                return self._cache
            return []

    def get_latest_light(self) -> Optional[Dict]:
        """取得最近一期的燈號"""
        data = self.get_business_cycle_score()
        if data:
            return data[-1]
        return None

# 單例
ndc_adapter = NDCAdapter()
