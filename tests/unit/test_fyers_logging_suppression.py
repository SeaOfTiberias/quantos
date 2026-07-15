"""
FyersBroker.connect() — SDK Debug-Logging Suppression
────────────────────────────────────────────────────────
fyers_apiv3's FyersModel unconditionally attaches a FileHandler per logger
(api_logger, request_logger) and hardcodes request_logger to DEBUG
regardless of what we pass in — every single API call gets written to
fyersApi.log/fyersRequests.log for the life of the process, unbounded disk
growth (found while investigating a VM OOM incident). connect() caps each
handler's own level to CRITICAL right after construction.
"""

import logging
from unittest.mock import MagicMock, patch

from core.brokers.fyers import FyersBroker


def _config():
    return {
        "credentials": {
            "api_key": "app-id",
            "access_token": "test-token",
        },
    }


class TestSdkFileHandlerSuppression:

    def test_caps_both_logger_handlers_to_critical(self):
        api_handler = MagicMock(spec=logging.Handler)
        request_handler = MagicMock(spec=logging.Handler)
        mock_client = MagicMock()
        mock_client.api_logger.handlers = [api_handler]
        mock_client.request_logger.handlers = [request_handler]
        mock_client.get_profile.return_value = {"code": 200, "data": {"name": "Test User"}}

        with patch("fyers_apiv3.fyersModel.FyersModel", return_value=mock_client):
            broker = FyersBroker(config=_config())
            assert broker.connect() is True

        api_handler.setLevel.assert_called_once_with(logging.CRITICAL)
        request_handler.setLevel.assert_called_once_with(logging.CRITICAL)

    def test_tolerates_missing_logger_attributes(self):
        """Defensive getattr(..., None)/getattr(..., []) — must not raise if
        a future SDK version renames/removes api_logger or request_logger."""
        mock_client = MagicMock(spec=["get_profile"])
        mock_client.get_profile.return_value = {"code": 200, "data": {"name": "Test User"}}

        with patch("fyers_apiv3.fyersModel.FyersModel", return_value=mock_client):
            broker = FyersBroker(config=_config())
            assert broker.connect() is True
