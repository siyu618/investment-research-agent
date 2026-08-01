"""Cross-process determinism tests for the Mock provider.

Verifies that two separate Python processes generate IDENTICAL mock
data and snapshot hashes for the same stock — no builtin hash(),
no per-process randomness.
"""

import json
import subprocess
import sys
import textwrap

import pytest


def _gen_code() -> str:
    """Script that emits a JSON payload for 600519.SH mock data."""
    return textwrap.dedent("""
        import asyncio, json
        from tools.providers import MockMarketDataProvider
        from runtime.snapshot import DataSnapshot

        async def main():
            p = MockMarketDataProvider()
            stocks = await p.get_stock_basic(ts_codes=['600519.SH'])
            prices = await p.get_daily_price('600519.SH', '20240101', '20240201')
            fin = await p.get_financial_summary('600519.SH', '20220101', '20251231')
            val = await p.get_valuation('600519.SH')
            snap = DataSnapshot.build(
                source='mock', stocks=stocks,
                prices={'600519.SH': prices},
                financials={'600519.SH': fin},
                valuation={'600519.SH': val},
            )
            d = snap.to_dict()
            last_close = d['prices']['600519.SH'][-1]['close']
            print(json.dumps({
                'content_hash': snap.content_hash,
                'stock_count': len(d['stocks']),
                'price_count': len(d['prices']['600519.SH']),
                'fin_count': len(d['financials']['600519.SH']),
                'last_close': last_close,
                'pe': d['valuation']['600519.SH']['pe'],
                'pb': d['valuation']['600519.SH']['pb'],
            }, default=str))

        asyncio.run(main())
    """)


def _run_subprocess(code: str) -> dict:
    """Run a snippet in a fresh python subprocess and parse its JSON output."""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"subprocess failed: {result.stderr}"
    lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
    return json.loads(lines[-1])


class TestCrossProcessDeterminism:
    def test_two_processes_identical_hash(self):
        code = _gen_code()
        a = _run_subprocess(code)
        b = _run_subprocess(code)
        assert a["content_hash"] == b["content_hash"], (
            "Mock snapshot content hash differs across processes"
        )

    def test_two_processes_identical_prices(self):
        code = _gen_code()
        a = _run_subprocess(code)
        b = _run_subprocess(code)
        assert a["last_close"] == b["last_close"]
        assert a["price_count"] == b["price_count"]

    def test_two_processes_identical_valuation(self):
        code = _gen_code()
        a = _run_subprocess(code)
        b = _run_subprocess(code)
        assert a["pe"] == b["pe"]
        assert a["pb"] == b["pb"]

    def test_no_builtin_hash_in_providers(self):
        """Providers module must not use Python builtin hash()."""
        import inspect

        from tools import providers as mod

        src = inspect.getsource(mod)
        lines = [l for l in src.splitlines() if "hash(" in l]
        bad_lines = [
            l for l in lines
            if "hash_of" not in l and "_stable_seed" not in l
            and "sha256" not in l and "data_hash" not in l
        ]
        assert bad_lines == [], f"Builtin hash() usage found: {bad_lines}"
