import unittest

from tradingagents.execution.alpaca_executor import normalize_order_inputs


class TestAlpacaOrderNormalization(unittest.TestCase):
    def test_limit_falls_back_to_offset(self):
        spec, err = normalize_order_inputs(
            default_order_type="limit",
            default_time_in_force="DAY",
            side="BUY",
            current_price=100.0,
            limit_price_offset_pct=0.01,
            agent_order_type="LIMIT",
            agent_limit_price=None,
        )
        self.assertIsNone(err)
        self.assertEqual(spec.order_type, "LIMIT")
        self.assertEqual(spec.limit_price, 101.0)

    def test_limit_uses_agent_price(self):
        spec, err = normalize_order_inputs(
            default_order_type="market",
            default_time_in_force="DAY",
            side="SELL",
            current_price=100.0,
            limit_price_offset_pct=0.01,
            agent_order_type="LIMIT",
            agent_limit_price=99.5,
        )
        self.assertIsNone(err)
        self.assertEqual(spec.limit_price, 99.5)

    def test_stop_requires_stop_price(self):
        spec, err = normalize_order_inputs(
            default_order_type="market",
            default_time_in_force="DAY",
            side="SELL",
            current_price=100.0,
            limit_price_offset_pct=0.01,
            agent_order_type="STOP",
            agent_stop_price=None,
        )
        self.assertIsNone(spec)
        self.assertIn("STOP_PRICE", err)

    def test_stop_limit_requires_both_prices(self):
        spec, err = normalize_order_inputs(
            default_order_type="market",
            default_time_in_force="DAY",
            side="SELL",
            current_price=100.0,
            limit_price_offset_pct=0.01,
            agent_order_type="STOP_LIMIT",
            agent_stop_price=95.0,
            agent_limit_price=None,
        )
        self.assertIsNone(spec)
        self.assertIn("LIMIT_PRICE", err)

    def test_trailing_stop_requires_exactly_one(self):
        spec, err = normalize_order_inputs(
            default_order_type="market",
            default_time_in_force="DAY",
            side="SELL",
            current_price=100.0,
            limit_price_offset_pct=0.01,
            agent_order_type="TRAILING_STOP",
            agent_trail_percent=3,
            agent_trail_price=1.25,
        )
        self.assertIsNone(spec)
        self.assertIn("exactly one", err.lower())

    def test_invalid_order_type_errors(self):
        spec, err = normalize_order_inputs(
            default_order_type="market",
            default_time_in_force="DAY",
            side="BUY",
            current_price=100.0,
            limit_price_offset_pct=0.01,
            agent_order_type="ICEBERG",
        )
        self.assertIsNone(spec)
        self.assertIn("Unsupported ORDER_TYPE", err)

    def test_invalid_time_in_force_errors(self):
        spec, err = normalize_order_inputs(
            default_order_type="market",
            default_time_in_force="DAY",
            side="BUY",
            current_price=100.0,
            limit_price_offset_pct=0.01,
            agent_order_type="MARKET",
            agent_time_in_force="IOC",
        )
        self.assertIsNone(spec)
        self.assertIn("TIME_IN_FORCE", err)


if __name__ == "__main__":
    unittest.main()

