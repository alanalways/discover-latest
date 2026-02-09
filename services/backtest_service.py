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
        "martingale": "馬丁格爾策略",
    }
    
    def __init__(self):
        self.commission_rate = 0.001425  # 手續費 0.1425%
        self.tax_rate = 0.003  # 台股證交稅 0.3%
    
    def run_backtest(
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
        elif strategy == "martingale":
            # 馬丁格爾使用專用模擬器
            return self._run_martingale(history, params, initial_capital)
        else:
            return {"error": f"不支援的策略: {strategy}"}
        
        # 模擬交易
        trades = self._simulate_trades(history, signals, initial_capital, position_size)
        
        # 建立每日權益曲線
        equity_curve = self._build_equity_curve(history, trades, initial_capital)
        
        # 計算績效指標
        metrics = self._calculate_metrics(trades, history, initial_capital, equity_curve)
        
        return {
            "strategy": strategy,
            "strategy_name": self.STRATEGIES.get(strategy, strategy),
            "params": params,
            "initial_capital": initial_capital,
            "trades": trades,
            "metrics": metrics,
            "equity_curve": equity_curve,
        }
    
    def _get_default_params(self, strategy: str) -> Dict:
        """取得策略預設參數"""
        defaults = {
            "ma_cross": {"short_period": 5, "long_period": 20},
            "breakout": {"period": 20, "threshold": 0.02},
            "momentum": {"period": 14, "threshold": 0.05},
            "rsi": {"period": 14, "oversold": 30, "overbought": 70},
            "martingale": {
                "multiplier": 2.0,        # 虧損倍率
                "max_layers": 5,           # 最大加碼層數
                "max_position_pct": 0.5,   # 最大倉位佔比 (50%)
                "stop_loss_pct": 0.10,     # 停損 10%
                "take_profit_pct": 0.05,   # 停利 5%
                "commission": 0.001425,    # 手續費
                "slippage": 0.001,         # 滑價 0.1%
                "base_amount_pct": 0.02,   # 基礎買入金額佔比 2%
            },
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
    
    def _build_equity_curve(
        self, history: List[Dict], trades: List[Dict], initial_capital: float
    ) -> List[float]:
        """建立逐日權益曲線"""
        trade_map = {}
        for t in trades:
            d = t.get("date", "")
            trade_map[d] = t.get("capital_after", None)

        equity = [initial_capital]
        shares = 0
        cash = initial_capital
        entry_price = 0

        for h in history:
            d = h.get("date", "")
            close = h.get("close", 0)
            if d in trade_map:
                cash = trade_map[d]
                # 判斷是否仍有持倉
                for t in trades:
                    if t.get("date") == d:
                        action = t.get("action", "")
                        if "買入" in action or "買" in action:
                            shares = t.get("shares", 0)
                            entry_price = t.get("price", close)
                        elif "賣出" in action or "結算" in action:
                            shares = 0
            total = cash + shares * close
            equity.append(total)

        return equity[:len(history)]

    def _calculate_metrics(
        self,
        trades: List[Dict],
        history: List[Dict],
        initial_capital: float,
        equity_curve: List[float] = None,
    ) -> Dict[str, Any]:
        """計算績效指標（含 Sharpe Ratio）"""
        if not trades:
            return {
                "total_return": 0, "total_return_pct": 0, "win_rate": 0,
                "total_trades": 0, "max_drawdown": 0, "sharpe_ratio": 0,
                "profit_factor": 0,
            }

        final_capital = trades[-1].get("capital_after", initial_capital)
        total_return = final_capital - initial_capital
        total_return_pct = (final_capital / initial_capital - 1) * 100

        sell_trades = [t for t in trades if t.get("action") == "賣出" or "賣出" in t.get("action", "")]
        winning_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
        win_rate = len(winning_trades) / len(sell_trades) * 100 if sell_trades else 0

        # 最大回撤
        eq = equity_curve or [initial_capital]
        max_drawdown = 0.0
        peak = eq[0]
        for v in eq:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100 if peak > 0 else 0
            max_drawdown = max(max_drawdown, dd)

        # 平均獲利/虧損
        avg_win = sum(t.get("pnl", 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
        losing_trades = [t for t in sell_trades if t.get("pnl", 0) <= 0]
        avg_loss = sum(t.get("pnl", 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0

        # Profit Factor
        gross_profit = sum(t.get("pnl", 0) for t in winning_trades)
        gross_loss = abs(sum(t.get("pnl", 0) for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Sharpe Ratio（日收益 → 年化）
        sharpe_ratio = 0.0
        if len(eq) > 2:
            daily_returns = []
            for i in range(1, len(eq)):
                if eq[i - 1] > 0:
                    daily_returns.append((eq[i] - eq[i - 1]) / eq[i - 1])
            if daily_returns:
                mean_r = sum(daily_returns) / len(daily_returns)
                var_r = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
                std_r = math.sqrt(var_r) if var_r > 0 else 0
                sharpe_ratio = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0

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
            "profit_factor": round(profit_factor, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
        }


    # ===== 馬丁格爾策略（專用模擬器）=====

    def _run_martingale(
        self,
        history: List[Dict],
        params: Dict,
        initial_capital: float,
    ) -> Dict[str, Any]:
        """
        馬丁格爾策略回測（含風控）
        
        風控機制：
        - 倍率限制 (multiplier)
        - 最大層數限制 (max_layers)
        - 最大倉位占比限制 (max_position_pct)
        - 停損/停利
        - 手續費 + 滑價
        """
        if params is None:
            params = self._get_default_params("martingale")
        
        multiplier = params.get("multiplier", 2.0)
        max_layers = params.get("max_layers", 5)
        max_position_pct = params.get("max_position_pct", 0.5)
        stop_loss_pct = params.get("stop_loss_pct", 0.10)
        take_profit_pct = params.get("take_profit_pct", 0.05)
        commission = params.get("commission", 0.001425)
        slippage = params.get("slippage", 0.001)
        base_amount_pct = params.get("base_amount_pct", 0.02)
        
        capital = initial_capital
        total_shares = 0
        total_cost = 0.0
        avg_price = 0.0
        current_layer = 0
        trades = []
        equity_curve = [initial_capital]
        peak_equity = initial_capital
        max_drawdown = 0.0
        capital_exhausted = False
        
        for i in range(1, len(history)):
            price = float(history[i].get("close", 0))
            prev_price = float(history[i - 1].get("close", 0))
            date = history[i].get("date", "")
            
            if price <= 0 or prev_price <= 0:
                continue
            
            daily_return = (price - prev_price) / prev_price
            
            # 計算當前持倉市值
            position_value = total_shares * price
            total_equity = capital + position_value
            
            # 記錄權益曲線
            equity_curve.append(total_equity)
            
            # 最大回撤
            if total_equity > peak_equity:
                peak_equity = total_equity
            dd = (peak_equity - total_equity) / peak_equity * 100
            max_drawdown = max(max_drawdown, dd)
            
            # 資金耗盡檢查
            if total_equity <= initial_capital * 0.1:
                capital_exhausted = True
                trades.append({
                    "date": date,
                    "action": "資金耗盡停止",
                    "price": price,
                    "shares": 0,
                    "capital_after": total_equity,
                    "layer": current_layer,
                    "reason": "資金不足 10%，強制停止"
                })
                break
            
            # 持倉停損
            if total_shares > 0 and avg_price > 0:
                unrealized_pnl_pct = (price - avg_price) / avg_price
                
                # 停利：達到目標獲利
                if unrealized_pnl_pct >= take_profit_pct:
                    proceeds = total_shares * price * (1 - commission - slippage)
                    pnl = proceeds - total_cost
                    capital += proceeds
                    trades.append({
                        "date": date,
                        "action": "停利賣出",
                        "price": price,
                        "shares": total_shares,
                        "proceeds": round(proceeds, 2),
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(unrealized_pnl_pct * 100, 2),
                        "capital_after": round(capital, 2),
                        "layer": current_layer,
                        "reason": f"停利 +{unrealized_pnl_pct*100:.1f}%"
                    })
                    total_shares = 0
                    total_cost = 0
                    avg_price = 0
                    current_layer = 0
                    continue
                
                # 停損：虧損超過限制
                if unrealized_pnl_pct <= -stop_loss_pct:
                    proceeds = total_shares * price * (1 - commission - slippage)
                    pnl = proceeds - total_cost
                    capital += proceeds
                    trades.append({
                        "date": date,
                        "action": "停損賣出",
                        "price": price,
                        "shares": total_shares,
                        "proceeds": round(proceeds, 2),
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(unrealized_pnl_pct * 100, 2),
                        "capital_after": round(capital, 2),
                        "layer": current_layer,
                        "reason": f"停損 {unrealized_pnl_pct*100:.1f}%"
                    })
                    total_shares = 0
                    total_cost = 0
                    avg_price = 0
                    current_layer = 0
                    continue
            
            # 馬丁格爾加碼邏輯：價格下跌時加碼
            if daily_return < -0.01:  # 日跌幅 > 1%
                if current_layer < max_layers:
                    # 計算加碼金額
                    layer_amount = initial_capital * base_amount_pct * (multiplier ** current_layer)
                    
                    # 倉位限制
                    current_position_pct = position_value / total_equity if total_equity > 0 else 0
                    if current_position_pct >= max_position_pct:
                        continue
                    
                    # 資金限制
                    layer_amount = min(layer_amount, capital * 0.9)
                    if layer_amount < price:
                        continue
                    
                    buy_price = price * (1 + slippage)
                    shares = int(layer_amount / buy_price)
                    if shares <= 0:
                        continue
                    
                    cost = shares * buy_price * (1 + commission)
                    
                    if cost > capital:
                        continue
                    
                    capital -= cost
                    total_cost += cost
                    total_shares += shares
                    avg_price = total_cost / total_shares if total_shares > 0 else 0
                    current_layer += 1
                    
                    trades.append({
                        "date": date,
                        "action": f"加碼買入 L{current_layer}",
                        "price": round(buy_price, 2),
                        "shares": shares,
                        "cost": round(cost, 2),
                        "capital_after": round(capital, 2),
                        "layer": current_layer,
                        "avg_price": round(avg_price, 2),
                        "reason": f"日跌 {daily_return*100:.1f}%，第 {current_layer} 層加碼"
                    })
            
            # 無持倉時的初始買入
            elif total_shares == 0 and daily_return < -0.005:
                layer_amount = initial_capital * base_amount_pct
                buy_price = price * (1 + slippage)
                shares = int(layer_amount / buy_price)
                if shares <= 0:
                    continue
                
                cost = shares * buy_price * (1 + commission)
                if cost > capital:
                    continue
                
                capital -= cost
                total_cost = cost
                total_shares = shares
                avg_price = buy_price
                current_layer = 1
                
                trades.append({
                    "date": date,
                    "action": "初始買入 L1",
                    "price": round(buy_price, 2),
                    "shares": shares,
                    "cost": round(cost, 2),
                    "capital_after": round(capital, 2),
                    "layer": 1,
                    "avg_price": round(avg_price, 2),
                    "reason": f"日跌 {daily_return*100:.1f}%，建立初始倉位"
                })
        
        # 結算：若仍有持倉，以最後一日收盤價平倉
        if total_shares > 0 and history:
            last_price = float(history[-1].get("close", 0))
            proceeds = total_shares * last_price * (1 - commission - slippage)
            pnl = proceeds - total_cost
            capital += proceeds
            trades.append({
                "date": history[-1].get("date", ""),
                "action": "期末結算",
                "price": last_price,
                "shares": total_shares,
                "proceeds": round(proceeds, 2),
                "pnl": round(pnl, 2),
                "capital_after": round(capital, 2),
                "layer": current_layer,
                "reason": "回測結束，強制平倉"
            })
        
        # 績效計算
        final_capital = capital
        total_return = final_capital - initial_capital
        total_return_pct = (final_capital / initial_capital - 1) * 100
        
        sell_trades = [t for t in trades if "賣出" in t.get("action", "") or t.get("action") == "期末結算"]
        win_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
        lose_trades = [t for t in sell_trades if t.get("pnl", 0) <= 0]
        
        # 最大連續虧損層數
        max_layer_reached = max((t.get("layer", 0) for t in trades), default=0)
        
        metrics = {
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "final_capital": round(final_capital, 2),
            "total_trades": len(sell_trades),
            "winning_trades": len(win_trades),
            "losing_trades": len(lose_trades),
            "win_rate": round(len(win_trades) / len(sell_trades) * 100, 1) if sell_trades else 0,
            "max_drawdown": round(max_drawdown, 2),
            "max_layer_reached": max_layer_reached,
            "capital_exhausted": capital_exhausted,
        }
        
        # 風險提示（必做）
        risk_warnings = [
            "馬丁格爾策略在連續虧損時資金需求呈指數增長，可能導致資金耗盡。",
            f"本次回測最大回撤: {max_drawdown:.1f}%",
            f"最高加碼層數: {max_layer_reached} 層（上限 {max_layers} 層）",
        ]
        if capital_exhausted:
            risk_warnings.append("⚠️ 本次回測中資金已耗盡，策略失敗！")
        if max_drawdown > 30:
            risk_warnings.append("⚠️ 最大回撤超過 30%，策略風險極高！")
        
        return {
            "strategy": "martingale",
            "strategy_name": "馬丁格爾策略",
            "params": params,
            "initial_capital": initial_capital,
            "trades": trades,
            "metrics": metrics,
            "risk_warnings": risk_warnings,
            "equity_curve": equity_curve,
        }


# 單例
backtest_service = BacktestService()
