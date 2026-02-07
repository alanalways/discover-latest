"""
Backtest Service - 回測服務
提供均線、突破、動能等策略的歷史回測功能
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import math


class BacktestService:
    """回測服務"""
    
    # 策略類型
    STRATEGIES = {
        "ma_cross": "均線交叉",
        "breakout": "突破策略",
        "momentum": "動能策略",
        "rsi": "RSI 策略",
    }
    
    def __init__(self):
        self.commission_rate = 0.001425  # 手續費 0.1425%
        self.tax_rate = 0.003  # 台股證交稅 0.3%
    
    async def run_backtest(
        self,
        history: List[Dict],
        strategy: str = "ma_cross",
        params: Dict = None,
        initial_capital: float = 1000000,
        position_size: float = 1.0
    ) -> Dict[str, Any]:
        """
        執行回測
        
        Args:
            history: 歷史資料
            strategy: 策略類型
            params: 策略參數
            initial_capital: 初始資金
            position_size: 每次交易佔比（0-1）
        
        Returns:
            回測結果
        """
        if not history or len(history) < 30:
            return {"error": "歷史資料不足"}
        
        if params is None:
            params = self._get_default_params(strategy)
        
        # 執行策略
        if strategy == "ma_cross":
            signals = self._ma_cross_strategy(history, params)
        elif strategy == "breakout":
            signals = self._breakout_strategy(history, params)
        elif strategy == "momentum":
            signals = self._momentum_strategy(history, params)
        elif strategy == "rsi":
            signals = self._rsi_strategy(history, params)
        else:
            return {"error": f"不支援的策略: {strategy}"}
        
        # 模擬交易
        trades = self._simulate_trades(history, signals, initial_capital, position_size)
        
        # 計算績效指標
        metrics = self._calculate_metrics(trades, history, initial_capital)
        
        return {
            "strategy": strategy,
            "strategy_name": self.STRATEGIES.get(strategy, strategy),
            "params": params,
            "initial_capital": initial_capital,
            "trades": trades,
            "metrics": metrics
        }
    
    def _get_default_params(self, strategy: str) -> Dict:
        """取得策略預設參數"""
        defaults = {
            "ma_cross": {"short_period": 5, "long_period": 20},
            "breakout": {"period": 20, "threshold": 0.02},
            "momentum": {"period": 14, "threshold": 0.05},
            "rsi": {"period": 14, "oversold": 30, "overbought": 70},
        }
        return defaults.get(strategy, {})
    
    def _ma_cross_strategy(self, history: List[Dict], params: Dict) -> List[Dict]:
        """
        均線交叉策略
        短均線上穿長均線 → 買入
        短均線下穿長均線 → 賣出
        """
        short_period = params.get("short_period", 5)
        long_period = params.get("long_period", 20)
        
        prices = [h.get("close", 0) for h in history]
        
        signals = []
        position = 0  # 0: 無持倉, 1: 持有
        
        for i in range(long_period, len(prices)):
            short_ma = sum(prices[i-short_period+1:i+1]) / short_period
            long_ma = sum(prices[i-long_period+1:i+1]) / long_period
            
            prev_short_ma = sum(prices[i-short_period:i]) / short_period
            prev_long_ma = sum(prices[i-long_period:i]) / long_period
            
            # 黃金交叉（買入）
            if prev_short_ma <= prev_long_ma and short_ma > long_ma and position == 0:
                signals.append({
                    "date": history[i]["date"],
                    "signal": "buy",
                    "price": prices[i],
                    "reason": f"短均線({short_period}) 上穿 長均線({long_period})"
                })
                position = 1
            
            # 死亡交叉（賣出）
            elif prev_short_ma >= prev_long_ma and short_ma < long_ma and position == 1:
                signals.append({
                    "date": history[i]["date"],
                    "signal": "sell",
                    "price": prices[i],
                    "reason": f"短均線({short_period}) 下穿 長均線({long_period})"
                })
                position = 0
        
        return signals
    
    def _breakout_strategy(self, history: List[Dict], params: Dict) -> List[Dict]:
        """
        突破策略
        價格突破 N 日高點 → 買入
        價格跌破 N 日低點 → 賣出
        """
        period = params.get("period", 20)
        threshold = params.get("threshold", 0.02)
        
        signals = []
        position = 0
        
        for i in range(period, len(history)):
            current_price = history[i].get("close", 0)
            
            # 計算 N 日高低點
            period_highs = [h.get("high", 0) for h in history[i-period:i]]
            period_lows = [h.get("low", 0) for h in history[i-period:i]]
            
            high = max(period_highs)
            low = min(period_lows)
            
            # 突破高點買入
            if current_price > high * (1 + threshold) and position == 0:
                signals.append({
                    "date": history[i]["date"],
                    "signal": "buy",
                    "price": current_price,
                    "reason": f"突破 {period} 日高點 {high:.2f}"
                })
                position = 1
            
            # 跌破低點賣出
            elif current_price < low * (1 - threshold) and position == 1:
                signals.append({
                    "date": history[i]["date"],
                    "signal": "sell",
                    "price": current_price,
                    "reason": f"跌破 {period} 日低點 {low:.2f}"
                })
                position = 0
        
        return signals
    
    def _momentum_strategy(self, history: List[Dict], params: Dict) -> List[Dict]:
        """
        動能策略
        價格漲幅超過閾值 → 買入
        價格跌幅超過閾值 → 賣出
        """
        period = params.get("period", 14)
        threshold = params.get("threshold", 0.05)
        
        signals = []
        position = 0
        
        for i in range(period, len(history)):
            current_price = history[i].get("close", 0)
            past_price = history[i-period].get("close", 0)
            
            if past_price == 0:
                continue
            
            momentum = (current_price - past_price) / past_price
            
            # 正向動能買入
            if momentum > threshold and position == 0:
                signals.append({
                    "date": history[i]["date"],
                    "signal": "buy",
                    "price": current_price,
                    "reason": f"動能 +{momentum*100:.1f}% 超過閾值"
                })
                position = 1
            
            # 負向動能賣出
            elif momentum < -threshold and position == 1:
                signals.append({
                    "date": history[i]["date"],
                    "signal": "sell",
                    "price": current_price,
                    "reason": f"動能 {momentum*100:.1f}% 低於閾值"
                })
                position = 0
        
        return signals
    
    def _rsi_strategy(self, history: List[Dict], params: Dict) -> List[Dict]:
        """
        RSI 策略
        RSI < 超賣區 → 買入
        RSI > 超買區 → 賣出
        """
        period = params.get("period", 14)
        oversold = params.get("oversold", 30)
        overbought = params.get("overbought", 70)
        
        # 計算 RSI
        rsi_values = self._calculate_rsi(history, period)
        
        signals = []
        position = 0
        
        for i in range(period, len(history)):
            rsi = rsi_values[i - period] if i - period < len(rsi_values) else 50
            price = history[i].get("close", 0)
            
            # 超賣買入
            if rsi < oversold and position == 0:
                signals.append({
                    "date": history[i]["date"],
                    "signal": "buy",
                    "price": price,
                    "reason": f"RSI = {rsi:.1f} < {oversold} (超賣)"
                })
                position = 1
            
            # 超買賣出
            elif rsi > overbought and position == 1:
                signals.append({
                    "date": history[i]["date"],
                    "signal": "sell",
                    "price": price,
                    "reason": f"RSI = {rsi:.1f} > {overbought} (超買)"
                })
                position = 0
        
        return signals
    
    def _calculate_rsi(self, history: List[Dict], period: int = 14) -> List[float]:
        """計算 RSI"""
        prices = [h.get("close", 0) for h in history]
        rsi_values = []
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
        
        for i in range(period - 1, len(gains)):
            avg_gain = sum(gains[i-period+1:i+1]) / period
            avg_loss = sum(losses[i-period+1:i+1]) / period
            
            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            
            rsi_values.append(rsi)
        
        return rsi_values
    
    def _simulate_trades(
        self,
        history: List[Dict],
        signals: List[Dict],
        initial_capital: float,
        position_size: float
    ) -> List[Dict]:
        """模擬交易"""
        trades = []
        capital = initial_capital
        shares = 0
        entry_price = 0
        
        for signal in signals:
            price = signal["price"]
            
            if signal["signal"] == "buy" and shares == 0:
                # 買入
                trade_amount = capital * position_size
                shares = int(trade_amount / price)
                cost = shares * price * (1 + self.commission_rate)
                capital -= cost
                entry_price = price
                
                trades.append({
                    "date": signal["date"],
                    "action": "買入",
                    "price": price,
                    "shares": shares,
                    "cost": cost,
                    "capital_after": capital,
                    "reason": signal["reason"]
                })
            
            elif signal["signal"] == "sell" and shares > 0:
                # 賣出
                proceeds = shares * price * (1 - self.commission_rate - self.tax_rate)
                pnl = proceeds - shares * entry_price - shares * entry_price * self.commission_rate
                pnl_pct = (price - entry_price) / entry_price * 100
                capital += proceeds
                
                trades.append({
                    "date": signal["date"],
                    "action": "賣出",
                    "price": price,
                    "shares": shares,
                    "proceeds": proceeds,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "capital_after": capital,
                    "reason": signal["reason"]
                })
                
                shares = 0
                entry_price = 0
        
        return trades
    
    def _calculate_metrics(
        self,
        trades: List[Dict],
        history: List[Dict],
        initial_capital: float
    ) -> Dict[str, Any]:
        """計算績效指標"""
        if not trades:
            return {
                "total_return": 0,
                "total_return_pct": 0,
                "win_rate": 0,
                "total_trades": 0,
                "max_drawdown": 0,
                "sharpe_ratio": 0
            }
        
        # 計算總報酬
        final_capital = trades[-1].get("capital_after", initial_capital)
        total_return = final_capital - initial_capital
        total_return_pct = (final_capital / initial_capital - 1) * 100
        
        # 計算勝率
        sell_trades = [t for t in trades if t.get("action") == "賣出"]
        winning_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
        win_rate = len(winning_trades) / len(sell_trades) * 100 if sell_trades else 0
        
        # 計算最大回撤
        equity_curve = [initial_capital]
        for trade in trades:
            equity_curve.append(trade.get("capital_after", equity_curve[-1]))
        
        max_drawdown = 0
        peak = equity_curve[0]
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak * 100
            max_drawdown = max(max_drawdown, drawdown)
        
        # 計算平均獲利/虧損
        avg_win = sum(t.get("pnl", 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
        losing_trades = [t for t in sell_trades if t.get("pnl", 0) <= 0]
        avg_loss = sum(t.get("pnl", 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        # 計算 Profit Factor
        gross_profit = sum(t.get("pnl", 0) for t in winning_trades)
        gross_loss = abs(sum(t.get("pnl", 0) for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        return {
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "final_capital": round(final_capital, 2),
            "total_trades": len(sell_trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "max_drawdown": round(max_drawdown, 2),
            "profit_factor": round(profit_factor, 2)
        }


# 單例
backtest_service = BacktestService()
