"""A small Asterisk REST Interface client."""
import asyncio
import json
import logging

import aiohttp

log = logging.getLogger("moxdialer.ari")


class Ari:
    def __init__(self, base, user, password, app="moxdialer"):
        self.base = base.rstrip("/")
        self.app = app
        self.auth = aiohttp.BasicAuth(user, password)
        self.session = None

    async def start(self):
        self.session = aiohttp.ClientSession(auth=self.auth)

    async def close(self):
        if self.session:
            await self.session.close()

    async def call(self, method, path, **params):
        clean = {key: value for key, value in params.items() if value is not None}
        async with self.session.request(method, f"{self.base}/ari{path}", params=clean) as response:
            if response.status >= 400:
                text = await response.text()
                raise RuntimeError(f"ARI {method} {path}: {response.status} {text[:200]}")
            if response.content_type == "application/json":
                return await response.json()
            return None

    async def quiet(self, method, path, **params):
        """For cleanup, where the thing may already be gone."""
        try:
            return await self.call(method, path, **params)
        except (RuntimeError, aiohttp.ClientError) as error:
            log.debug("%s", error)
            return None

    async def events(self, handler):
        """Stream events forever, reconnecting if Asterisk restarts."""
        url = self.base.replace("http", "ws", 1) + "/ari/events"
        while True:
            try:
                async with self.session.ws_connect(url, params={"app": self.app, "subscribeAll": "false"}, heartbeat=30) as socket:
                    log.info("Connected to Asterisk")
                    async for message in socket:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            try:
                                await handler(json.loads(message.data))
                            except Exception:
                                log.exception("Event failed")
            except (aiohttp.ClientError, OSError) as error:
                log.warning("Asterisk not reachable: %s", error)
            await asyncio.sleep(3)
