"""Coverage tests for dominionsc __main__ block."""

import runpy
import sys
from unittest.mock import patch


def test_main_block():
    """Test __main__ executes main() when run as __main__."""
    # Ensure module is reloaded/executed as __main__
    if "dominionsc.__main__" in sys.modules:
        del sys.modules["dominionsc.__main__"]
    if "dominionsc.cli" in sys.modules:
        # keep cli but patch main
        pass
    with patch("dominionsc.cli.main") as mock_main:
        runpy.run_module("dominionsc", run_name="__main__", alter_sys=True)
    mock_main.assert_called_once()
