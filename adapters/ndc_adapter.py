
import requests
import json
from datetime import datetime
from typing import List, Dict, Optional

class NDCAdapter:
    """國發會資料 Adapter (National Development Council)"""
    
    LIGHTSCORE_URL = 'https://index.ndc.gov.tw/n/json/lightscore'

    def get_business_cycle_score(self) -> List[Dict]:
        """
        取得台灣景氣對策信號分數
        回傳欄位: date (YYYYMM), score, light (藍/黃藍/綠/黃紅/紅)
        """
        try:
            res = requests.post(self.LIGHTSCORE_URL, timeout=10)
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
            return result
            
        except Exception as e:
            print(f"[NDC] 取得景氣燈號失敗: {e}")
            return []

    def get_latest_light(self) -> Optional[Dict]:
        """取得最近一期的燈號"""
        data = self.get_business_cycle_score()
        if data:
            return data[-1]
        return None

# 單例
ndc_adapter = NDCAdapter()
