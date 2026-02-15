from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from .catalyst_news import CatalystNewsScanner
from .macro_sector import MacroSectorScanner
from .models import DEFAULT_SCREENING_UNIVERSE, IntelligenceResult
from .technical_momentum import TechnicalMomentumScanner


class IntelligenceScanner:
    """
    Top-level orchestrator that runs all three sub-agents in parallel
    and merges their outputs into a single IntelligenceResult.
    """

    def __init__(self, llm, config: Optional[Dict[str, Any]] = None):
        self.llm = llm
        self.config = config or {}

        self.sector_scanner = MacroSectorScanner(llm=llm, config=config)
        self.catalyst_scanner = CatalystNewsScanner(llm=llm, config=config)
        self.technical_scanner = TechnicalMomentumScanner(llm=llm, config=config)
        self.logger = logging.getLogger(self.__class__.__name__)

    def scan_all(
        self,
        trade_date: str,
        universe: Optional[List[str]] = None,
        focus_tickers: Optional[List[str]] = None,
        max_workers: int = 3,
    ) -> IntelligenceResult:
        import time

        start_time = time.time()
        universe = universe or DEFAULT_SCREENING_UNIVERSE
        result = IntelligenceResult(scan_date=trade_date)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            sector_future = pool.submit(self.sector_scanner.scan, trade_date)
            catalyst_future = pool.submit(self.catalyst_scanner.scan, trade_date, focus_tickers)
            technical_future = pool.submit(self.technical_scanner.scan, universe, trade_date)

            try:
                result.sector_signals = sector_future.result(timeout=120)
                self.logger.info(f"Sector scan: {len(result.sector_signals)} sectors ranked")
            except Exception as e:
                result.errors.append(f"Sector scan failed: {e}")
                self.logger.error(f"Sector scan failed: {e}")

            try:
                result.catalyst_signals = catalyst_future.result(timeout=120)
                self.logger.info(f"Catalyst scan: {len(result.catalyst_signals)} catalysts found")
            except Exception as e:
                result.errors.append(f"Catalyst scan failed: {e}")
                self.logger.error(f"Catalyst scan failed: {e}")

            try:
                result.technical_signals = technical_future.result(timeout=180)
                self.logger.info(f"Technical scan: {len(result.technical_signals)} tickers screened")
            except Exception as e:
                result.errors.append(f"Technical scan failed: {e}")
                self.logger.error(f"Technical scan failed: {e}")

        result.scan_duration_secs = round(time.time() - start_time, 1)
        aligned = result.tickers_with_multi_signal_alignment()
        self.logger.info(
            f"Intelligence scan complete in {result.scan_duration_secs}s. "
            f"Hot sectors: {[s.etf for s in result.hot_sectors]}, "
            f"Breakout candidates: {[t.ticker for t in result.breakout_candidates]}, "
            f"Multi-signal aligned: {aligned}"
        )
        return result

    def scan_with_dynamic_universe(
        self,
        trade_date: str,
        base_universe: Optional[List[str]] = None,
        excluded_tickers: Optional[List[str]] = None,
    ) -> IntelligenceResult:
        excluded_set = {
            str(t).strip().upper()
            for t in (excluded_tickers or [])
            if str(t).strip()
        }
        base_universe = [
            t for t in (base_universe or DEFAULT_SCREENING_UNIVERSE)
            if str(t).strip().upper() not in excluded_set
        ]

        with ThreadPoolExecutor(max_workers=2) as pool:
            sector_future = pool.submit(self.sector_scanner.scan, trade_date)
            catalyst_future = pool.submit(self.catalyst_scanner.scan, trade_date, None, 3)

            sector_signals = []
            catalyst_signals = []
            try:
                sector_signals = sector_future.result(timeout=120)
            except Exception as e:
                self.logger.error(f"Phase 1 sector scan failed: {e}")
            try:
                catalyst_signals = catalyst_future.result(timeout=120)
            except Exception as e:
                self.logger.error(f"Phase 1 catalyst scan failed: {e}")

        expanded_universe = set(base_universe)
        for c in catalyst_signals:
            if c.ticker and len(c.ticker) <= 5 and c.ticker.isalpha():
                t = c.ticker.upper()
                if t not in excluded_set:
                    expanded_universe.add(t)

        self.logger.info(
            f"Universe expanded from {len(base_universe)} to {len(expanded_universe)} "
            f"tickers based on Phase 1 intelligence"
        )

        try:
            technical_signals = self.technical_scanner.scan(
                [t for t in expanded_universe if str(t).strip().upper() not in excluded_set],
                trade_date,
            )
        except Exception as e:
            self.logger.error(f"Phase 2 technical scan failed: {e}")
            technical_signals = []

        if excluded_set:
            technical_signals = [
                s for s in technical_signals
                if str(getattr(s, "ticker", "")).upper() not in excluded_set
            ]

        result = IntelligenceResult(
            sector_signals=sector_signals,
            catalyst_signals=catalyst_signals,
            technical_signals=technical_signals,
            scan_date=trade_date,
        )

        aligned = result.tickers_with_multi_signal_alignment()
        self.logger.info(f"Dynamic scan complete. Multi-signal aligned tickers: {aligned}")
        return result
