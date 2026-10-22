"""Presets and env-driven settings."""

from scamantiq.config import PRESETS, load_settings


def test_cloud_presets_point_at_current_models():
    assert PRESETS["deepseek"]["model"] == "deepseek-flash"  # deepseek-chat was retired on 2026-07-24
    assert PRESETS["anthropic"]["model"] == "claude-haiku-5-5"


def test_effort_comes_from_env(monkeypatch):
    monkeypatch.delenv("SCAMANTIQ_EFFORT", raising=False)
    assert load_settings(preset="mock").effort == ""
    monkeypatch.setenv("SCAMANTIQ_EFFORT", "low")
    assert load_settings(preset="mock").effort == "low"
