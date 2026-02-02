"""
Portfolio-level analysis and rebalancing engine.
Analyzes all positions, generates recommendations, and provides strategic insights.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.execution import AlpacaExecutor
from tradingagents.execution.portfolio_context import fetch_portfolio_context


class PortfolioAnalyzer:
    """
    Analyzes entire portfolio and generates rebalancing recommendations.
    """

    def __init__(
        self,
        graph: TradingAgentsGraph,
        executor: AlpacaExecutor,
        analysis_date: Optional[str] = None
    ):
        self.graph = graph
        self.executor = executor
        self.analysis_date = analysis_date or datetime.now().strftime("%Y-%m-%d")
        self.logger = logging.getLogger("PortfolioAnalyzer")

    def analyze_portfolio(
        self,
        execute_trades: bool = False,
        min_conviction: float = 60.0
    ) -> Dict[str, Any]:
        """
        Analyze all portfolio positions and generate recommendations.

        Args:
            execute_trades: Whether to execute recommended trades
            min_conviction: Minimum conviction score (0-100) to execute trades

        Returns:
            Dict with analysis results, recommendations, and insights
        """
        self.logger.info(f"Starting portfolio analysis for {self.analysis_date}")

        # Step 1: Fetch current portfolio
        portfolio = self._fetch_portfolio()
        if not portfolio or portfolio['positions_count'] == 0:
            return {
                "error": "No positions found in portfolio",
                "portfolio": portfolio
            }

        self.logger.info(f"Analyzing {portfolio['positions_count']} positions")

        # Step 2: Analyze each position
        position_analyses = self._analyze_positions(portfolio['positions'])

        # Step 3: Perform portfolio-level analysis
        portfolio_metrics = self._calculate_portfolio_metrics(
            portfolio, position_analyses
        )

        # Step 4: Generate recommendations
        recommendations = self._generate_recommendations(
            portfolio, position_analyses, portfolio_metrics
        )

        # Step 5: Execute trades if requested
        execution_results = []
        if execute_trades:
            execution_results = self._execute_recommendations(
                recommendations, min_conviction
            )

        # Step 6: Generate strategic insights
        strategic_insights = self._generate_strategic_insights(
            portfolio, position_analyses, portfolio_metrics, recommendations
        )

        return {
            "analysis_date": self.analysis_date,
            "portfolio_summary": portfolio,
            "portfolio_metrics": portfolio_metrics,
            "position_analyses": position_analyses,
            "recommendations": recommendations,
            "execution_results": execution_results,
            "strategic_insights": strategic_insights
        }

    def _fetch_portfolio(self) -> Dict[str, Any]:
        """Fetch current portfolio state from Alpaca."""
        try:
            return self.executor.get_portfolio_summary()
        except Exception as e:
            self.logger.error(f"Failed to fetch portfolio: {e}")
            return {}

    def _analyze_positions(
        self, positions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analyze each position using the trading agents framework."""
        analyses = []

        for position in positions:
            ticker = position['symbol']
            self.logger.info(f"Analyzing position: {ticker}")

            try:
                # Run full analysis with portfolio context
                portfolio_ctx = fetch_portfolio_context(ticker)
                final_state, decision = self.graph.propagate(
                    ticker, self.analysis_date, portfolio_context=portfolio_ctx
                )

                # Extract structured decision
                structured = self.graph.extract_structured_decision(
                    final_state['final_trade_decision']
                )

                # Calculate conviction score
                conviction = self._calculate_position_conviction(
                    final_state, decision
                )

                analyses.append({
                    "ticker": ticker,
                    "current_qty": position['qty'],
                    "current_value": position['market_value'],
                    "unrealized_pl": position['unrealized_pl'],
                    "unrealized_plpc": position['unrealized_plpc'],
                    "decision": decision,
                    "structured_decision": structured,
                    "conviction_score": conviction,
                    "final_state": final_state,
                    "analysis_summary": self._extract_summary(final_state)
                })

            except Exception as e:
                self.logger.error(f"Error analyzing {ticker}: {e}")
                analyses.append({
                    "ticker": ticker,
                    "error": str(e),
                    "decision": "HOLD",
                    "conviction_score": 0
                })

        return analyses

    def _calculate_portfolio_metrics(
        self,
        portfolio: Dict[str, Any],
        analyses: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate portfolio-level metrics."""
        total_value = portfolio['account_value']
        positions = portfolio['positions']

        # Position concentration
        max_position_pct = max(
            (p['market_value'] / total_value * 100) for p in positions
        ) if positions else 0

        # Sector allocation (simplified - would need sector data in practice)
        # This is a placeholder
        sector_allocation = self._estimate_sector_allocation(positions)

        # Win/loss ratio
        winners = sum(1 for p in positions if float(p['unrealized_pl']) > 0)
        losers = sum(1 for p in positions if float(p['unrealized_pl']) < 0)

        # Average conviction across portfolio
        avg_conviction = sum(
            a.get('conviction_score', 0) for a in analyses
        ) / len(analyses) if analyses else 0

        # Risk indicators
        sell_signals = sum(1 for a in analyses if a.get('decision') == 'SELL')
        buy_signals = sum(1 for a in analyses if a.get('decision') == 'BUY')

        return {
            "total_value": total_value,
            "cash": portfolio['cash'],
            "buying_power": portfolio['buying_power'],
            "position_count": len(positions),
            "max_position_pct": round(max_position_pct, 2),
            "sector_allocation": sector_allocation,
            "win_loss_ratio": f"{winners}/{losers}",
            "avg_conviction": round(avg_conviction, 2),
            "sell_signals": sell_signals,
            "buy_signals": buy_signals,
            "portfolio_health": self._assess_portfolio_health(
                max_position_pct, avg_conviction, winners, losers
            )
        }

    def _generate_recommendations(
        self,
        portfolio: Dict[str, Any],
        analyses: List[Dict[str, Any]],
        metrics: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate actionable recommendations for portfolio rebalancing."""
        recommendations = []

        for analysis in analyses:
            if 'error' in analysis:
                continue

            ticker = analysis['ticker']
            decision = analysis['decision']
            conviction = analysis['conviction_score']
            current_value = analysis['current_value']

            # Portfolio-aware recommendation
            position_pct = (current_value / portfolio['account_value']) * 100

            rec = {
                "ticker": ticker,
                "action": decision,
                "conviction": conviction,
                "current_position_pct": round(position_pct, 2),
                "rationale": self._build_rationale(analysis, metrics),
                "priority": self._calculate_priority(decision, conviction, position_pct),
                "suggested_action": None,
                "decision_summary": None,
            }

            # Specific action suggestions
            if decision == "SELL":
                if conviction > 70:
                    rec["suggested_action"] = f"SELL ALL ({analysis['current_qty']} shares)"
                elif conviction > 50:
                    rec["suggested_action"] = f"SELL 50% ({int(analysis['current_qty'] * 0.5)} shares)"
                else:
                    rec["suggested_action"] = f"SELL 25% ({int(analysis['current_qty'] * 0.25)} shares)"

            elif decision == "BUY":
                # Don't recommend buying more if position is already large
                if position_pct > 15:
                    rec["suggested_action"] = "HOLD - Position already large"
                    rec["action"] = "HOLD"
                elif conviction > 70 and portfolio['cash'] > 1000:
                    add_pct = min(5, portfolio['cash'] / portfolio['account_value'] * 100)
                    rec["suggested_action"] = f"ADD {add_pct:.1f}% more to position"
                else:
                    rec["suggested_action"] = "HOLD - Maintain position"
                    rec["action"] = "HOLD"

            else:  # HOLD
                rec["suggested_action"] = "HOLD - No action needed"

            rec["decision_summary"] = self._summarize_recommendation(rec)
            recommendations.append(rec)

        # Sort by priority
        recommendations.sort(key=lambda x: x['priority'], reverse=True)

        return recommendations

    def _summarize_recommendation(self, rec: Dict[str, Any]) -> str:
        """Create a 1-2 sentence summary suitable for reports."""
        rationale = (rec.get("rationale") or "").strip()
        suggested = (rec.get("suggested_action") or "").strip()
        parts = []
        if rationale:
            parts.append(rationale.rstrip(".") + ".")
        if suggested:
            parts.append(f"Suggested: {suggested.rstrip('.')}.")
        return self._to_sentence_summary(" ".join(parts).strip(), max_sentences=2)

    def _to_sentence_summary(self, text: str, max_sentences: int = 2) -> str:
        """Keep only the first N sentence-like chunks."""
        s = (text or "").strip()
        if not s:
            return ""

        # Simple sentence splitter (good enough for report summaries).
        out = []
        buf = []
        for ch in s:
            buf.append(ch)
            if ch in ".!?":
                sentence = "".join(buf).strip()
                if sentence:
                    out.append(sentence)
                buf = []
                if len(out) >= max_sentences:
                    break
        if len(out) < max_sentences and buf:
            tail = "".join(buf).strip()
            if tail:
                out.append(tail)

        summary = " ".join(out).strip()
        return summary

    def _execute_recommendations(
        self,
        recommendations: List[Dict[str, Any]],
        min_conviction: float
    ) -> List[Dict[str, Any]]:
        """Execute high-conviction recommendations."""
        results = []

        for rec in recommendations:
            if rec['action'] == 'HOLD':
                continue

            if rec['conviction'] < min_conviction:
                self.logger.info(
                    f"Skipping {rec['ticker']} - conviction {rec['conviction']} "
                    f"below threshold {min_conviction}"
                )
                continue

            ticker = rec['ticker']
            action = rec['action']

            self.logger.info(
                f"Executing {action} for {ticker} (conviction: {rec['conviction']})"
            )

            try:
                # For portfolio rebalancing, we need to handle partial sells
                # and position additions differently than the standard executor
                result = self.executor.execute_signal(
                    ticker=ticker,
                    signal=action,
                    analysis_state=None,  # Could pass full state if needed
                    trade_date=self.analysis_date
                )

                results.append({
                    "ticker": ticker,
                    "action": action,
                    "conviction": rec['conviction'],
                    "execution_result": result
                })

            except Exception as e:
                self.logger.error(f"Execution failed for {ticker}: {e}")
                results.append({
                    "ticker": ticker,
                    "action": action,
                    "error": str(e)
                })

        return results

    def _generate_strategic_insights(
        self,
        portfolio: Dict[str, Any],
        analyses: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        recommendations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate forward-looking strategic insights."""
        insights = {
            "portfolio_assessment": self._assess_overall_portfolio(metrics),
            "key_risks": self._identify_key_risks(analyses, metrics),
            "opportunities": self._identify_opportunities(analyses, portfolio),
            "rebalancing_needs": self._assess_rebalancing_needs(metrics, recommendations),
            "future_actions": self._suggest_future_actions(analyses, metrics, portfolio)
        }

        return insights

    # ======== Helper methods ======== #

    def _calculate_position_conviction(
        self, final_state: Dict[str, Any], decision: str
    ) -> float:
        """Calculate conviction score for a position (reuse from batch_analysis.py)."""
        score = 0.0

        if decision == "BUY":
            score = 60
        elif decision == "SELL":
            score = 60  # SELL signals also indicate conviction
        else:
            score = 40  # HOLD is neutral

        final_text = final_state.get("final_trade_decision", "").lower()

        # Positive conviction markers
        if any(word in final_text for word in ["strong", "compelling", "excellent"]):
            score += 10
        if any(word in final_text for word in ["high confidence", "strongly recommend"]):
            score += 10

        # Negative conviction markers
        if any(word in final_text for word in ["uncertain", "mixed", "unclear"]):
            score -= 10

        return max(0, min(100, score))

    def _extract_summary(self, final_state: Dict[str, Any]) -> str:
        """Extract key summary from analysis."""
        decision = final_state.get('final_trade_decision', '')
        # Extract first 200 chars as summary
        return decision[:200] + "..." if len(decision) > 200 else decision

    def _estimate_sector_allocation(self, positions: List[Dict]) -> Dict[str, float]:
        """Estimate sector allocation (placeholder - needs real sector data)."""
        # In production, you'd fetch sector data from a provider
        return {
            "Technology": 40.0,
            "Finance": 25.0,
            "Healthcare": 20.0,
            "Other": 15.0
        }

    def _assess_portfolio_health(
        self, max_position_pct: float, avg_conviction: float, 
        winners: int, losers: int
    ) -> str:
        """Assess overall portfolio health."""
        if max_position_pct > 20:
            return "ATTENTION: Over-concentrated"
        elif avg_conviction < 50:
            return "CAUTION: Low average conviction"
        elif winners < losers:
            return "CAUTION: More losers than winners"
        elif avg_conviction > 70 and winners > losers:
            return "HEALTHY: Strong positions"
        else:
            return "FAIR: Mixed signals"

    def _build_rationale(
        self, analysis: Dict[str, Any], metrics: Dict[str, Any]
    ) -> str:
        """Build rationale for recommendation."""
        decision = analysis['decision']
        conviction = analysis['conviction_score']
        pl_pct = analysis.get('unrealized_plpc', 0) * 100

        rationale_parts = []

        if decision == "SELL":
            rationale_parts.append(f"Agent recommends SELL with {conviction}% conviction.")
            if pl_pct < -10:
                rationale_parts.append(f"Position down {abs(pl_pct):.1f}%, cutting losses.")
            elif pl_pct > 20:
                rationale_parts.append(f"Position up {pl_pct:.1f}%, taking profits.")

        elif decision == "BUY":
            rationale_parts.append(f"Agent recommends BUY with {conviction}% conviction.")
            if pl_pct > 0:
                rationale_parts.append(f"Position up {pl_pct:.1f}%, adding to winner.")
            else:
                rationale_parts.append("Opportunity to average up position.")

        else:
            rationale_parts.append(f"Agent recommends HOLD ({conviction}% conviction).")

        return " ".join(rationale_parts)

    def _calculate_priority(
        self, decision: str, conviction: float, position_pct: float
    ) -> float:
        """Calculate priority score for recommendation."""
        priority = conviction

        # High priority for large positions that need attention
        if decision == "SELL" and position_pct > 15:
            priority += 20

        # Lower priority for small positions
        if position_pct < 5:
            priority -= 10

        return max(0, min(100, priority))

    def _assess_overall_portfolio(self, metrics: Dict[str, Any]) -> str:
        """Assess overall portfolio state."""
        health = metrics['portfolio_health']
        sell_signals = metrics['sell_signals']
        
        if "HEALTHY" in health:
            return "Portfolio is in good shape with strong positions."
        elif sell_signals > metrics['position_count'] / 2:
            return f"CAUTION: {sell_signals} positions showing SELL signals - consider rebalancing."
        else:
            return f"Portfolio status: {health}. Monitor positions closely."

    def _identify_key_risks(
        self, analyses: List[Dict], metrics: Dict[str, Any]
    ) -> List[str]:
        """Identify key portfolio risks."""
        risks = []

        if metrics['max_position_pct'] > 20:
            risks.append(
                f"Over-concentration: Largest position is {metrics['max_position_pct']:.1f}% "
                "of portfolio (>20% threshold)"
            )

        high_loss_positions = [
            a for a in analyses 
            if a.get('unrealized_plpc', 0) < -0.15  # Down 15%+
        ]
        if high_loss_positions:
            tickers = [a['ticker'] for a in high_loss_positions]
            risks.append(
                f"Significant losses in {len(tickers)} positions: {', '.join(tickers)}"
            )

        if metrics['avg_conviction'] < 50:
            risks.append(
                f"Low average conviction ({metrics['avg_conviction']:.1f}) "
                "suggests weak portfolio positioning"
            )

        return risks if risks else ["No major risks identified"]

    def _identify_opportunities(
        self, analyses: List[Dict], portfolio: Dict[str, Any]
    ) -> List[str]:
        """Identify opportunities in the portfolio."""
        opportunities = []

        # High conviction BUY signals
        strong_buys = [
            a for a in analyses 
            if a.get('decision') == 'BUY' and a.get('conviction_score', 0) > 70
        ]
        if strong_buys:
            tickers = [a['ticker'] for a in strong_buys]
            opportunities.append(
                f"Strong BUY signals in existing positions: {', '.join(tickers)}"
            )

        # Underperforming positions with turnaround potential
        turnarounds = [
            a for a in analyses
            if (a.get('unrealized_plpc', 0) < 0 and 
                a.get('decision') == 'BUY' and 
                a.get('conviction_score', 0) > 60)
        ]
        if turnarounds:
            tickers = [a['ticker'] for a in turnarounds]
            opportunities.append(
                f"Potential turnaround opportunities: {', '.join(tickers)}"
            )

        # Cash deployment
        cash_pct = (portfolio['cash'] / portfolio['account_value']) * 100
        if cash_pct > 10:
            opportunities.append(
                f"{cash_pct:.1f}% cash available for deployment in high-conviction ideas"
            )

        return opportunities if opportunities else ["No immediate opportunities identified"]

    def _assess_rebalancing_needs(
        self, metrics: Dict[str, Any], recommendations: List[Dict]
    ) -> str:
        """Assess whether portfolio needs rebalancing."""
        high_priority = sum(1 for r in recommendations if r['priority'] > 70)

        if high_priority >= 3:
            return f"URGENT: {high_priority} high-priority actions needed"
        elif metrics['sell_signals'] > 2:
            return f"MODERATE: {metrics['sell_signals']} positions need attention"
        else:
            return "MINIMAL: Portfolio is relatively well-balanced"

    def _suggest_future_actions(
        self, analyses: List[Dict], metrics: Dict[str, Any], 
        portfolio: Dict[str, Any]
    ) -> List[str]:
        """Suggest future strategic actions."""
        suggestions = []

        # Diversification suggestions
        if metrics['position_count'] < 8:
            suggestions.append(
                "Consider adding 2-3 new positions to improve diversification"
            )

        # Sector allocation
        if metrics['max_position_pct'] > 20:
            suggestions.append(
                "Reduce largest position to improve risk distribution"
            )

        # Cash management
        cash_pct = (portfolio['cash'] / portfolio['account_value']) * 100
        if cash_pct < 5:
            suggestions.append(
                "Consider raising cash (currently <5%) for flexibility"
            )
        elif cash_pct > 20:
            suggestions.append(
                f"Deploy excess cash ({cash_pct:.1f}%) into high-conviction opportunities"
            )

        # Performance monitoring
        low_conviction = [
            a for a in analyses if a.get('conviction_score', 0) < 40
        ]
        if low_conviction:
            tickers = [a['ticker'] for a in low_conviction]
            suggestions.append(
                f"Monitor low-conviction positions closely: {', '.join(tickers)}"
            )

        # Regular rebalancing
        suggestions.append(
            "Schedule monthly portfolio review to maintain optimal allocation"
        )

        return suggestions
