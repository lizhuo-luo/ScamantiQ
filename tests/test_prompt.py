"""The system prompt must carry the taxonomy and the boundary rules that keep legitimate messages unflagged."""

from scamantiq.prompt import system_prompt
from scamantiq.taxonomy import TACTICS


def test_system_prompt_lists_every_tactic():
    sp = system_prompt()
    for t in TACTICS:
        assert f"- {t.label} ({t.name})" in sp


def test_system_prompt_says_a_brand_name_alone_is_not_impersonation():
    sp = system_prompt()
    assert "merely names its sender" in sp
    assert "quote the identity claim itself" in sp


def test_system_prompt_says_otp_warnings_are_not_isolation():
    sp = system_prompt()
    assert "one-time code" in sp
    assert "not isolation" in sp.lower()
