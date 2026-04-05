"""Regression checks for release-critical frontend contract fixes."""

from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "frontend" / "app.js"


def test_show_manual_form_targets_existing_onboarding_cards():
    source = APP_JS.read_text()

    assert "document.getElementById('ob-card-import')" not in source
    assert "const linkCard = document.getElementById('ob-card-link');" in source


def test_rerun_onboarding_uses_patch_contract():
    source = APP_JS.read_text()

    assert "await api('/auth/onboarding-complete', { method: 'PATCH', body: JSON.stringify({ complete: false }) });" in source
