"""Market Researcher : formule le prompt de recherche et délègue au routeur (stage research)."""
from engine.researcher import run_market_research


class FakeRouter:
    def __init__(self):
        self.calls = []

    async def generate_text(self, stage, prompt, use_search=False):
        self.calls.append({"stage": stage, "prompt": prompt, "use_search": use_search})
        return ("Prix neuf ~600€, occasion ~350€.", "gemini-3.1-flash-lite", 1)


async def test_run_market_research_returns_text():
    r = FakeRouter()
    text = await run_market_research(r, "iPhone 13 128Go")
    assert text == "Prix neuf ~600€, occasion ~350€."


async def test_run_market_research_uses_research_stage_with_search():
    r = FakeRouter()
    await run_market_research(r, "iPhone 13 128Go")
    call = r.calls[-1]
    assert call["stage"] == "research"
    assert call["use_search"] is True
    # le titre de la recherche est injecté dans le prompt
    assert "iPhone 13 128Go" in call["prompt"]
