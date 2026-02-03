import os
import unittest
from contextlib import contextmanager


@contextmanager
def _temp_env(values: dict[str, str | None]):
    old = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestAlpacaDataUrlResolution(unittest.TestCase):
    def test_infers_data_url_from_paper_trading_base_url(self):
        from tradingagents.dataflows import alpaca as alpaca_mod

        with _temp_env(
            {
                "ALPACA_API_KEY": "test",
                "ALPACA_SECRET_KEY": "test",
                "APCA_API_DATA_URL": None,
                "ALPACA_DATA_URL": None,
                "APCA_API_BASE_URL": "https://paper-api.alpaca.markets",
                "ALPACA_API_BASE_URL": None,
                "APCA_ENDPOINT": None,
                "ALPACA_ENDPOINT": None,
            }
        ):
            creds = alpaca_mod._get_alpaca_credentials()
            self.assertEqual(creds.data_url, "https://data.alpaca.markets")

    def test_infers_data_url_from_live_trading_base_url(self):
        from tradingagents.dataflows import alpaca as alpaca_mod

        with _temp_env(
            {
                "ALPACA_API_KEY": "test",
                "ALPACA_SECRET_KEY": "test",
                "APCA_API_DATA_URL": None,
                "ALPACA_DATA_URL": None,
                "APCA_API_BASE_URL": "https://api.alpaca.markets/v2",
                "ALPACA_API_BASE_URL": None,
                "APCA_ENDPOINT": None,
                "ALPACA_ENDPOINT": None,
            }
        ):
            creds = alpaca_mod._get_alpaca_credentials()
            self.assertEqual(creds.data_url, "https://data.alpaca.markets")

    def test_explicit_data_url_wins_over_inference(self):
        from tradingagents.dataflows import alpaca as alpaca_mod

        with _temp_env(
            {
                "ALPACA_API_KEY": "test",
                "ALPACA_SECRET_KEY": "test",
                "APCA_API_DATA_URL": "https://data.alpaca.markets/v2",
                "ALPACA_DATA_URL": None,
                "APCA_API_BASE_URL": "https://paper-api.alpaca.markets",
            }
        ):
            creds = alpaca_mod._get_alpaca_credentials()
            self.assertEqual(creds.data_url, "https://data.alpaca.markets")

    def test_no_data_url_when_no_base_urls(self):
        from tradingagents.dataflows import alpaca as alpaca_mod

        with _temp_env(
            {
                "ALPACA_API_KEY": "test",
                "ALPACA_SECRET_KEY": "test",
                "APCA_API_DATA_URL": None,
                "ALPACA_DATA_URL": None,
                "APCA_API_BASE_URL": None,
                "ALPACA_API_BASE_URL": None,
                "APCA_ENDPOINT": None,
                "ALPACA_ENDPOINT": None,
            }
        ):
            creds = alpaca_mod._get_alpaca_credentials()
            self.assertIsNone(creds.data_url)

    def test_secret_key_fallbacks(self):
        from tradingagents.dataflows import alpaca as alpaca_mod

        with _temp_env(
            {
                "ALPACA_API_KEY": "test",
                "ALPACA_SECRET_KEY": None,
                "ALPACA_API_SECRET": "test-secret",
                "APCA_API_SECRET_KEY": None,
                "APCA_API_DATA_URL": None,
                "ALPACA_DATA_URL": None,
                "APCA_API_BASE_URL": "paper-api.alpaca.markets",
            }
        ):
            creds = alpaca_mod._get_alpaca_credentials()
            self.assertEqual(creds.secret_key, "test-secret")
            self.assertEqual(creds.data_url, "https://data.alpaca.markets")

