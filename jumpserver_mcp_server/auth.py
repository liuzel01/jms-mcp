"""JumpServer HTTP Signature authentication."""

import base64
import datetime
import hashlib
import hmac
from collections.abc import Generator

import httpx


class JumpServerSignatureAuth(httpx.Auth):
    """Sign requests with a JumpServer system-user access key."""

    requires_request_body = False

    def __init__(self, key_id: str, secret: str, organization: str) -> None:
        self._key_id = key_id
        self._secret = secret
        self._organization = organization

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        date = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        path = request.url.raw_path.decode("ascii")
        accept = request.headers.get("accept", "application/json")
        canonical = f"(request-target): {request.method.lower()} {path}\naccept: {accept}\ndate: {date}"
        signature = base64.b64encode(
            hmac.new(self._secret.encode(), canonical.encode(), hashlib.sha256).digest()
        ).decode()
        request.headers.update(
            {
                "Accept": accept,
                "Date": date,
                "X-JMS-ORG": self._organization,
                "Authorization": (
                    f'Signature keyId="{self._key_id}",algorithm="hmac-sha256",'
                    f'headers="(request-target) accept date",signature="{signature}"'
                ),
            }
        )
        yield request
