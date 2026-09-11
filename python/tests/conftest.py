"""Shared pytest configuration for the SDK's own test suite.

Enables the ``pytester`` fixture so ``tests/unit/test_conformance_plugin.py`` can
spawn throwaway pytest sessions that load our own ``pytest11`` plugin
(``donkey-kit[test]``, #191) and assert its end-to-end behaviour — inert
without the flag, a clean UsageError on misuse, a scenario table on success.
"""

from __future__ import annotations

pytest_plugins = ["pytester"]
