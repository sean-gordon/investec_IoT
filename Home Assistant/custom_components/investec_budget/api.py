"""Minimal async client for the Investec Programmable Banking (Private Banking) API."""
from __future__ import annotations

import base64
import logging
import time
from datetime import date
from typing import Any

import aiohttp

from .const import PROD_BASE, SANDBOX_BASE

_LOGGER = logging.getLogger(__name__)


class InvestecAuthError(Exception):
    """Credentials were rejected."""


class InvestecApiError(Exception):
    """Any other API or network failure."""


class InvestecClient:
    def __init__(self, session: aiohttp.ClientSession, client_id: str,
                 client_secret: str, api_key: str, sandbox: bool = False) -> None:
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_key = api_key
        self._base = SANDBOX_BASE if sandbox else PROD_BASE
        self._token: str | None = None
        self._token_expiry = 0.0
        self.include_pending = True

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry - 60:
            return self._token
        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        try:
            async with self._session.post(
                f"{self._base}/identity/v2/oauth2/token",
                headers={"Authorization": f"Basic {basic}", "x-api-key": self._api_key,
                         "Accept": "application/json"},
                data={"grant_type": "client_credentials"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status in (400, 401, 403):
                    raise InvestecAuthError(f"Token request rejected ({resp.status})")
                if resp.status != 200:
                    raise InvestecApiError(f"Token request failed ({resp.status})")
                body = await resp.json()
        except TimeoutError as err:
            raise InvestecApiError("Timed out requesting token") from err
        except aiohttp.ClientError as err:
            raise InvestecApiError(str(err)) from err
        self._token = body["access_token"]
        self._token_expiry = time.monotonic() + float(body.get("expires_in", 1799))
        return self._token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(2):
            token = await self._get_token()
            try:
                async with self._session.get(
                    f"{self._base}{path}", params=params,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        self._token = None  # Expired early; fetch a new token once.
                        continue
                    if resp.status in (401, 403):
                        raise InvestecAuthError(f"Request rejected ({resp.status})")
                    if resp.status != 200:
                        detail = (await resp.text())[:200].replace("\n", " ")
                        raise InvestecApiError(f"Request failed ({resp.status}) on {path}: {detail}")
                    return await resp.json()
            except TimeoutError as err:
                raise InvestecApiError(f"Timed out on {path}") from err
            except aiohttp.ClientError as err:
                raise InvestecApiError(f"{err} on {path}") from err
        raise InvestecAuthError("Request rejected after token refresh")

    async def accounts(self) -> list[dict[str, Any]]:
        body = await self._get("/za/pb/v1/accounts")
        return body.get("data", {}).get("accounts", [])

    async def available_balance(self, account_id: str) -> float:
        body = await self._get(f"/za/pb/v1/accounts/{account_id}/balance")
        data = body.get("data", {})
        return float(data.get("availableBalance", data.get("currentBalance", 0)) or 0)

    async def transactions(self, account_id: str, from_date: date, to_date: date) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        page = 1
        while True:
            params: dict[str, Any] = {"fromDate": from_date.isoformat(), "toDate": to_date.isoformat(), "page": page}
            # includePending: today's card purchases stay PENDING until they post (often the next
            # day); without this flag Investec leaves them out and today's spend reads R0.
            if self.include_pending:
                params["includePending"] = "true"
            try:
                body = await self._get(f"/za/pb/v1/accounts/{account_id}/transactions", params)
            except InvestecApiError as err:
                if self.include_pending and ("(400)" in str(err) or "Timed out" in str(err)):
                    _LOGGER.warning("Investec rejected includePending; continuing without it: %s", err)
                    self.include_pending = False
                    continue
                raise
            result.extend(body.get("data", {}).get("transactions", []))
            total_pages = int(body.get("meta", {}).get("totalPages", 1) or 1)
            if page >= total_pages or page >= 50:
                return result
            page += 1
