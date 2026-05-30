import asyncio

from engine.bootstrap import make_scrape_fn


async def test_make_scrape_fn_uses_browser_and_extractor():
    calls = {"goto": [], "extracted": False}

    class FakePage:
        async def goto(self, url, **kw):
            calls["goto"].append(url)
        async def wait_for_timeout(self, ms):
            pass
        async def close(self):
            pass

    class FakeContext:
        async def new_page(self):
            return FakePage()

    async def fake_get_context():
        return FakeContext()

    async def fake_extract(page):
        calls["extracted"] = True
        return [{"ad_id": "1", "title": "x", "price": 10.0, "url": "u", "city": None, "image_url": None}]

    lock = asyncio.Lock()
    scrape_fn = make_scrape_fn(fake_get_context, fake_extract, lock)
    ads = await scrape_fn("https://lbc/u1")

    assert calls["goto"] == ["https://lbc/u1"]
    assert calls["extracted"] is True
    assert ads[0]["ad_id"] == "1"
