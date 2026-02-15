from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .models import CatalystSignal
from .utils import parse_json_dict


CATALYST_SCANNER_SYSTEM_PROMPT = """You are a financial news catalyst analyst. Your ONLY job is to extract actionable trading catalysts from news.

You will receive recent financial news. For each news item that contains a SPECIFIC, ACTIONABLE catalyst:
- Identify the ticker symbol affected (if mentioned or clearly implied)
- Classify the catalyst type
- Score sentiment from -1.0 (very bearish) to +1.0 (very bullish)
- Rate actionability: "high" (trade within days), "medium" (watch list), "low" (background)

Catalyst types: earnings_beat, earnings_miss, analyst_upgrade, analyst_downgrade,
fda_approval, fda_rejection, merger_acquisition, product_launch, guidance_raise,
guidance_cut, regulatory_action, insider_buying, buyback_announced, sector_rotation,
macro_policy, geopolitical, other

Rules:
- ONLY include catalysts with clear stock-level implications
- Skip vague market commentary and opinion pieces
- Prioritize catalysts that are RECENT (within 3 days) and SPECIFIC
- If no clear ticker, include sector if identifiable
- Return ONLY JSON, no markdown

Return this JSON structure:
{
  "catalysts": [
    {
      "ticker": "NVDA",
      "sector": "Technology",
      "catalyst_type": "earnings_beat",
      "headline": "NVIDIA Q3 revenue tops estimates by 22%, raises guidance",
      "sentiment_score": 0.9,
      "recency_days": 1,
      "actionability": "high"
    }
  ],
  "dominant_narrative": "One sentence on the biggest theme in current news"
}"""


class CatalystNewsScanner:
    def __init__(self, llm, config: Optional[Dict[str, Any]] = None):
        self.llm = llm
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def _fetch_news(self, trade_date: str, look_back_days: int = 3) -> str:
        from tradingagents.dataflows.interface import route_to_vendor

        try:
            return route_to_vendor("get_global_news", trade_date, look_back_days, limit=20)
        except Exception as e:
            self.logger.warning(f"Global news fetch failed: {e}")
            return ""

    def _fetch_company_news_batch(self, tickers: List[str], trade_date: str, look_back_days: int = 3) -> str:
        from tradingagents.dataflows.interface import route_to_vendor

        end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=look_back_days)
        start_str = start_dt.strftime("%Y-%m-%d")

        all_news = []
        for ticker in tickers[:10]:
            try:
                news = route_to_vendor("get_news", ticker, start_str, trade_date)
                if news:
                    all_news.append(f"--- {ticker} ---\n{news}")
            except Exception as e:
                self.logger.debug(f"Company news for {ticker} failed: {e}")
                continue
        return "\n\n".join(all_news)

    def scan(
        self,
        trade_date: str,
        focus_tickers: Optional[List[str]] = None,
        look_back_days: int = 3,
    ) -> List[CatalystSignal]:
        news_text = self._fetch_news(trade_date, look_back_days)
        if focus_tickers:
            company_news = self._fetch_company_news_batch(focus_tickers, trade_date, look_back_days)
            if company_news:
                news_text += f"\n\n## Company-Specific News:\n{company_news}"

        if not news_text.strip():
            self.logger.warning("No news data available")
            return []

        max_news_chars = 8000
        if len(news_text) > max_news_chars:
            news_text = news_text[:max_news_chars] + "\n\n[... truncated for brevity ...]"

        try:
            result = self.llm.invoke(
                [
                    SystemMessage(content=CATALYST_SCANNER_SYSTEM_PROMPT),
                    HumanMessage(content=f"Date: {trade_date}\nLookback: {look_back_days} days\n\n{news_text}"),
                ]
            )
            content = result.content if hasattr(result, "content") else str(result)
            signals = self._parse_catalyst_response(content)
            if signals:
                return sorted(signals, key=lambda c: c.sentiment_score, reverse=True)
        except Exception as e:
            self.logger.warning(f"LLM catalyst extraction failed: {e}")
        return []

    def _parse_catalyst_response(self, response_text: str) -> Optional[List[CatalystSignal]]:
        data = parse_json_dict(response_text)
        if not data:
            return None
        catalysts = data.get("catalysts", [])
        if not catalysts:
            return None

        signals = []
        for c in catalysts:
            signals.append(
                CatalystSignal(
                    ticker=c.get("ticker", ""),
                    sector=c.get("sector", ""),
                    catalyst_type=c.get("catalyst_type", "other"),
                    headline=c.get("headline", ""),
                    sentiment_score=float(c.get("sentiment_score", 0)),
                    recency_days=int(c.get("recency_days", 0)),
                    actionability=c.get("actionability", "medium"),
                )
            )
        return signals if signals else None
