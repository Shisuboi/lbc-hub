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


async def test_make_scrape_fn_extracts_immediately_when_page_ready():
    """Avec un ready_selector, une page prête (annonces trouvées du 1er coup) n'attend qu'une fois."""
    calls = {"selector_waits": 0, "closed": False}

    class FakePage:
        async def goto(self, url, **kw):
            pass
        async def wait_for_selector(self, selector, timeout=None):
            calls["selector_waits"] += 1
            return object()  # trouvé immédiatement
        async def close(self):
            calls["closed"] = True

    class FakeContext:
        async def new_page(self):
            return FakePage()

    async def fake_get_context():
        return FakeContext()

    async def fake_extract(page):
        return [{"ad_id": "42"}]

    scrape_fn = make_scrape_fn(fake_get_context, fake_extract, asyncio.Lock(), ready_selector="a.ad")
    ads = await scrape_fn("u")

    assert calls["selector_waits"] == 1   # pas de 2e attente : page prête du 1er coup
    assert calls["closed"] is True
    assert ads[0]["ad_id"] == "42"


async def test_make_scrape_fn_waits_again_after_block_then_extracts():
    """Blocage Datadome : la 1re attente échoue, l'onglet reste ouvert et on ré-attend
    (résolution manuelle du captcha) avant d'extraire."""
    calls = {"selector_waits": 0, "closed": False}

    class FakePage:
        async def goto(self, url, **kw):
            pass
        async def wait_for_selector(self, selector, timeout=None):
            calls["selector_waits"] += 1
            if calls["selector_waits"] == 1:
                raise TimeoutError("pas d'annonces (captcha)")
            return object()  # 2e appel : l'humain a résolu le captcha
        async def close(self):
            calls["closed"] = True

    class FakeContext:
        async def new_page(self):
            return FakePage()

    async def fake_get_context():
        return FakeContext()

    async def fake_extract(page):
        return [{"ad_id": "7"}]

    scrape_fn = make_scrape_fn(fake_get_context, fake_extract, asyncio.Lock(), ready_selector="a.ad")
    ads = await scrape_fn("u")

    assert calls["selector_waits"] == 2   # 1 échec (blocage) + 1 ré-attente (résolu)
    assert calls["closed"] is True        # l'onglet est bien refermé à la fin
    assert ads[0]["ad_id"] == "7"


async def test_make_scrape_fn_sends_telegram_alert_on_captcha():
    """Captcha détecté : si telegram est passé, envoie une alerte."""
    calls = {"telegram_alerts": []}

    class FakePage:
        async def goto(self, url, **kw):
            pass
        async def wait_for_selector(self, selector, timeout=None):
            raise TimeoutError("captcha")
        async def close(self):
            pass

    class FakeContext:
        async def new_page(self):
            return FakePage()

    async def fake_get_context():
        return FakeContext()

    async def fake_extract(page):
        return []

    async def fake_telegram_send(client, text):
        calls["telegram_alerts"].append(text)

    class FakeTelegram:
        pass

    scrape_fn = make_scrape_fn(
        fake_get_context, fake_extract, asyncio.Lock(),
        ready_selector="a.ad", telegram=FakeTelegram()
    )
    # Monkey-patch send_alert au moment de l'appel
    import engine.bootstrap as bootstrap_mod
    old_send_alert = bootstrap_mod.send_alert
    bootstrap_mod.send_alert = fake_telegram_send
    try:
        ads = await scrape_fn("u")
        assert len(calls["telegram_alerts"]) == 1  # alerte envoyée une fois
        assert "Captcha" in calls["telegram_alerts"][0]
    finally:
        bootstrap_mod.send_alert = old_send_alert


async def test_make_scrape_fn_no_telegram_alert_without_client():
    """Sans client telegram, pas d'alerte même avec un captcha."""
    calls = {"selector_waits": 0, "closed": False}

    class FakePage:
        async def goto(self, url, **kw):
            pass
        async def wait_for_selector(self, selector, timeout=None):
            calls["selector_waits"] += 1
            if calls["selector_waits"] == 1:
                raise TimeoutError("pas d'annonces")
            return object()
        async def close(self):
            calls["closed"] = True

    class FakeContext:
        async def new_page(self):
            return FakePage()

    async def fake_get_context():
        return FakeContext()

    async def fake_extract(page):
        return [{"ad_id": "99"}]

    # telegram=None (défaut)
    scrape_fn = make_scrape_fn(fake_get_context, fake_extract, asyncio.Lock(), ready_selector="a.ad", telegram=None)
    ads = await scrape_fn("u")

    assert calls["selector_waits"] == 2
    assert calls["closed"] is True
    assert ads[0]["ad_id"] == "99"
