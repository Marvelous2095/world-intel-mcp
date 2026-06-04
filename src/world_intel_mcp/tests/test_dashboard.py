"""Tests for dashboard runner configuration."""

import pytest

from world_intel_mcp.dashboard.app import _parse_run_args


def test_parse_run_args_port() -> None:
    host, port = _parse_run_args(["--port", "8765"])

    assert host == "127.0.0.1"
    assert port == 8765


def test_parse_run_args_host_and_port() -> None:
    host, port = _parse_run_args(["--host", "0.0.0.0", "--port", "9000"])

    assert host == "0.0.0.0"
    assert port == 9000


def test_parse_run_args_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORLD_INTEL_DASHBOARD_HOST", "0.0.0.0")
    monkeypatch.setenv("WORLD_INTEL_DASHBOARD_PORT", "7777")

    host, port = _parse_run_args([])

    assert host == "0.0.0.0"
    assert port == 7777
