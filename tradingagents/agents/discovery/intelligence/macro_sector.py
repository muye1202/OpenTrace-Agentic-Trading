from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .models import SectorSignal
from .utils import parse_json_dict


SECTOR_SCANNER_SYSTEM_PROMPT = """You are a macro/sector rotation analyst. Your ONLY job is to rank sector momentum.

You will receive sector ETF performance data. Analyze it and return a JSON object.

Rules:
- Rank all sectors by momentum (1 = strongest)
- Calculate each sector's return relative to SPY (excess return)
- Note which sectors are ACCELERATING (10d return > 30d return implies acceleration)
- Write a 1-sentence narrative per sector explaining the driver
- Be concise and data-driven. No preamble, no markdown.

Return ONLY this JSON structure (no markdown fencing, no extra text):
{
  "sectors": [
    {
      "sector": "Technology",
      "etf": "XLK",
      "return_30d": 5.2,
      "return_10d": 3.1,
      "relative_to_spy": 2.1,
      "momentum_rank": 1,
      "narrative": "AI capex cycle driving semis and cloud names"
    }
  ],
  "market_regime": "risk-on | risk-off | mixed",
  "key_theme": "One sentence on the dominant macro theme"
}"""


class MacroSectorScanner:
    SECTOR_ETFS = {
        "XLK": "Technology",
        "XLF": "Financials",
        "XLE": "Energy",
        "XLV": "Healthcare",
        "XLY": "Consumer Discretionary",
        "XLP": "Consumer Staples",
        "XLI": "Industrials",
        "XLB": "Materials",
        "XLRE": "Real Estate",
        "XLU": "Utilities",
        "XLC": "Communication Services",
    }

    def __init__(self, llm, config: Optional[Dict[str, Any]] = None):
        self.llm = llm
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def _fetch_sector_returns(self, trade_date: str) -> List[Dict[str, Any]]:
        from tradingagents.dataflows.interface import route_to_vendor

        end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
        start_30d = (end_dt - timedelta(days=45)).strftime("%Y-%m-%d")
        all_tickers = list(self.SECTOR_ETFS.keys()) + ["SPY"]
        results = []

        for ticker in all_tickers:
            try:
                raw_csv = route_to_vendor("get_stock_data", ticker, start_30d, trade_date)
                lines = [l for l in raw_csv.split("\n") if l.strip() and not l.startswith("#")]
                if len(lines) < 3:
                    continue

                header = lines[0].split(",")
                close_idx = header.index("Close")
                date_idx = header.index("Date") if "Date" in header else 0

                prices = []
                for line in lines[1:]:
                    parts = line.split(",")
                    try:
                        prices.append({"date": parts[date_idx].strip(), "close": float(parts[close_idx])})
                    except (ValueError, IndexError):
                        continue

                if len(prices) < 5:
                    continue

                latest_close = prices[-1]["close"]
                first_close = prices[0]["close"]
                return_30d = ((latest_close - first_close) / first_close) * 100

                idx_10d = max(0, len(prices) - 10)
                close_10d = prices[idx_10d]["close"]
                return_10d = ((latest_close - close_10d) / close_10d) * 100

                results.append(
                    {
                        "ticker": ticker,
                        "sector": self.SECTOR_ETFS.get(ticker, "Benchmark"),
                        "return_30d": round(return_30d, 2),
                        "return_10d": round(return_10d, 2),
                        "latest_close": round(latest_close, 2),
                    }
                )
            except Exception as e:
                self.logger.warning(f"Failed to fetch {ticker}: {e}")
                continue

        return results

    def scan(self, trade_date: str) -> List[SectorSignal]:
        raw_data = self._fetch_sector_returns(trade_date)
        if not raw_data:
            self.logger.error("No sector data fetched")
            return []

        spy_data = next((d for d in raw_data if d["ticker"] == "SPY"), None)
        sector_data = [d for d in raw_data if d["ticker"] != "SPY"]

        spy_30d = spy_data["return_30d"] if spy_data else 0.0
        spy_10d = spy_data["return_10d"] if spy_data else 0.0
        for s in sector_data:
            s["relative_to_spy_30d"] = round(s["return_30d"] - spy_30d, 2)

        sector_data.sort(key=lambda x: x["return_30d"], reverse=True)
        for i, s in enumerate(sector_data):
            s["quant_rank"] = i + 1

        table = "Sector ETF Performance:\n"
        table += f"SPY (benchmark): 30d={spy_30d:+.2f}%, 10d={spy_10d:+.2f}%\n\n"
        table += "| Sector | ETF | 30d Return | 10d Return | vs SPY |\n"
        table += "|--------|-----|-----------|-----------|--------|\n"
        for s in sector_data:
            table += (
                f"| {s['sector']} | {s['ticker']} | {s['return_30d']:+.2f}% | "
                f"{s['return_10d']:+.2f}% | {s['relative_to_spy_30d']:+.2f}% |\n"
            )

        try:
            result = self.llm.invoke(
                [SystemMessage(content=SECTOR_SCANNER_SYSTEM_PROMPT), HumanMessage(content=f"Date: {trade_date}\n\n{table}")]
            )
            content = result.content if hasattr(result, "content") else str(result)
            signals = self._parse_sector_response(content)
            if signals:
                return signals
        except Exception as e:
            self.logger.warning(f"LLM sector analysis failed, using quant fallback: {e}")

        return self._quant_fallback(sector_data, spy_30d)

    def _parse_sector_response(self, response_text: str) -> Optional[List[SectorSignal]]:
        data = parse_json_dict(response_text)
        if not data:
            return None
        sectors = data.get("sectors", [])
        if not sectors:
            return None

        signals = []
        for s in sectors:
            signals.append(
                SectorSignal(
                    sector=s.get("sector", ""),
                    etf=s.get("etf", ""),
                    return_30d=float(s.get("return_30d", 0)),
                    return_10d=float(s.get("return_10d", 0)),
                    relative_to_spy=float(s.get("relative_to_spy", 0)),
                    momentum_rank=int(s.get("momentum_rank", 0)),
                    narrative=s.get("narrative", ""),
                )
            )
        return sorted(signals, key=lambda x: x.momentum_rank) if signals else None

    def _quant_fallback(self, sector_data: List[Dict], spy_30d: float) -> List[SectorSignal]:
        signals = []
        for s in sector_data:
            signals.append(
                SectorSignal(
                    sector=s["sector"],
                    etf=s["ticker"],
                    return_30d=s["return_30d"],
                    return_10d=s["return_10d"],
                    relative_to_spy=s.get("relative_to_spy_30d", s["return_30d"] - spy_30d),
                    momentum_rank=s["quant_rank"],
                    narrative="(quantitative ranking â€” LLM analysis unavailable)",
                )
            )
        return signals
