"""S5-8 — file-backed prompt loader + every shipped prompt renders cleanly."""

import pytest

from core.prompts import loader


@pytest.fixture
def tmp_prompts(tmp_path, monkeypatch):
    """Point the loader at an empty temp dir with a clean cache."""
    monkeypatch.setattr(loader, "PROMPTS_DIR", tmp_path)
    loader.clear_cache()
    yield tmp_path
    loader.clear_cache()


# ── Loader behaviour ──────────────────────────────────────────────────────────

def test_load_reads_and_strips(tmp_prompts):
    (tmp_prompts / "greet.md").write_text("\n  hello world  \n", encoding="utf-8")
    assert loader.load("greet") == "hello world"


def test_load_is_cached(tmp_prompts):
    f = tmp_prompts / "cached.md"
    f.write_text("first", encoding="utf-8")
    assert loader.load("cached") == "first"
    f.write_text("second", encoding="utf-8")  # cache should shadow the edit
    assert loader.load("cached") == "first"
    loader.clear_cache()
    assert loader.load("cached") == "second"


def test_missing_prompt_raises(tmp_prompts):
    with pytest.raises(loader.PromptNotFoundError):
        loader.load("nope")


def test_bad_name_rejected(tmp_prompts):
    for bad in ("a/b", "a\\b", "with.md"):
        with pytest.raises(ValueError):
            loader.load(bad)


def test_render_fills_placeholders(tmp_prompts):
    (tmp_prompts / "t.md").write_text("hi {name}, score {n:.1f}", encoding="utf-8")
    assert loader.render("t", name="TCS", n=82.4) == "hi TCS, score 82.4"


def test_render_keeps_literal_braces(tmp_prompts):
    (tmp_prompts / "j.md").write_text('{{"k": {v}}}', encoding="utf-8")
    assert loader.render("j", v=5) == '{"k": 5}'


def test_preload_missing_fails_fast(tmp_prompts):
    with pytest.raises(loader.PromptNotFoundError):
        loader.preload("does_not_exist")


# ── Every shipped prompt renders with representative inputs ────────────────────
# These use the REAL prompts/ dir (no fixture), exercising each template's
# placeholder set and brace-escaping so a typo can't slip through to a live
# Claude call. Kwargs mirror what each module passes.

_SYSTEM_PROMPTS = [
    "pre_trade_system",
    "options_recommender_system",
    "backtest_analyst_system",
    "screener_ranker_system",
]

_USER_RENDERS = {
    "pre_trade_user": dict(
        symbol="TCS", action="BUY", price=3456.789, timeframe="15m",
        strategy="darvas_breakout", confluence_score=82.4, notes="box breakout",
        classification="TRENDING", nifty_trend="UP", vix_signal="LOW",
        breadth_signal="POSITIVE", confidence=78,
        allowed_strategies="darvas_breakout", note_line="",
    ),
    "options_recommender_user": dict(
        underlying="NIFTY", regime_value="RANGING", confidence=71.0,
        trend_signal="FLAT", vix_signal="HIGH", spot_price=22500.0,
        days_to_expiry=5, iv_rank=68.0, iv_percentile=72.0, pcr=1.3,
        max_pain=22400.0, allowed_strategies="iron_condor, short_strangle",
    ),
    "morning_brief_user": dict(
        date_str="08 Jul 2026", regime="TRENDING_BULL", regime_confidence=80.0,
        trend_signal="UP", vix_signal="LOW", darvas_status="ENABLED",
        candidates_str="TCS (82)", events_str="None in 7-day window",
        kelly_size_pct=0.025, kelly_method="KELLY", prev_pnl_str="INR +12,300",
        open_positions_str="None",
    ),
    "alpha_attribution_user": dict(
        start_date="2026-07-01", end_date="2026-07-07",
        quantos_total_return=3.2, nifty_total_return=1.1, alpha=2.1,
        quantos_sharpe=1.4, quantos_win_rate=0.62,
        winners_str="SIG-1 (+4.2%)", losers_str="SIG-2 (-1.1%)",
    ),
    "backtest_analyst_user": dict(
        strategy_name="darvas", total_trades=120, win_rate=0.55,
        avg_win_pct=3.1, avg_loss_pct=-1.8, win_loss_ratio=1.7,
        profit_factor=1.9, sharpe_ratio=1.3, max_drawdown_pct=12.4,
        net_profit_pct=48.0, trades_per_month=4.2, avg_bars_held=9,
        year_block="  2024: ...", wf_block="  first...", flags="  None detected",
    ),
    "screener_ranker_user": dict(
        nifty_change_pct=0.8, n_candidates=12,
        candidates_block="- TCS: ...", top_n=5,
    ),
}


@pytest.mark.parametrize("name", _SYSTEM_PROMPTS)
def test_system_prompt_loads(name):
    text = loader.load(name)
    assert "QuantOS" in text and len(text) > 20


# Prompts that end with a literal JSON schema block (kept via {{ }} escaping).
_JSON_PROMPTS = {
    "options_recommender_user", "backtest_analyst_user", "screener_ranker_user",
}


@pytest.mark.parametrize("name,kwargs", list(_USER_RENDERS.items()))
def test_user_prompt_renders(name, kwargs):
    # render() would raise KeyError/IndexError on any unfilled or misspelled
    # placeholder, so a clean return already proves the placeholder set matches.
    out = loader.render(name, **kwargs)
    assert out
    if name in _JSON_PROMPTS:
        # Literal braces must survive .format() (proves {{ }} escaping is intact).
        assert "{" in out and "}" in out
    else:
        # A plain template has no braces once rendered; a stray one would mean
        # an un-escaped literal brace slipped in.
        assert "{" not in out and "}" not in out
