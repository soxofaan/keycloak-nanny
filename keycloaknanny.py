import random
import string
from typing import Optional, Set, TextIO
import logging
import dataclasses
import time

import requests

_log = logging.getLogger(__name__)


def enable_logging(
    *,
    level=logging.INFO,
    stream: Optional[TextIO] = None,
    fmt: str = "[%(levelname)s] %(name)s: %(message)s",
):
    """Simple logging setup to show what's going on behind the scenes."""
    _log.setLevel(level)
    handler = logging.StreamHandler(stream=stream)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt=fmt))
    _log.addHandler(handler)


def random_name(*, prefix: Optional[str] = None, length: int = 8, characters: Optional[str] = None) -> str:
    characters = characters or (string.ascii_letters + string.digits)
    name = "".join(random.choices(characters, k=length))
    return f"{prefix}{name}"


@dataclasses.dataclass(frozen=True)
class KcResource:
    type: str
    id: str
    name: str
    info: dict


@dataclasses.dataclass(frozen=True)
class _Tokens:
    expiry: int
    refresh_expiry: int
    token_data: dict


class KeycloakNanny:
    """
    Simple wrapper around the Keycloak admin REST API,
    to programmatically create realms, clients, users, ...
    """

    def __init__(
        self,
        root_url: str = "http://localhost:8080",
        admin: str = "admin",
        password: str = "admin",
    ):
        self.root_url = root_url
        self.admin = admin
        self.password = password
        self.default_realm = "master"
        self._tokens = _Tokens(0, 0, {})

    def _get_url(self, path: str) -> str:
        if path.startswith("/"):
            return self.root_url + path
        else:
            return path

    def _get_access_token(self, valid_for: int = 5) -> str:
        now = time.time()
        if self._tokens.expiry > now + valid_for:
            # Existing access token should work
            pass
        else:
            if self._tokens.refresh_expiry > now + valid_for:
                _log.info(f"Getting new access token {self.admin!r} using refresh token grant.")
                data = {
                    "client_id": "admin-cli",
                    "grant_type": "refresh_token",
                    "refresh_token": self._tokens.token_data["refresh_token"],
                }
            else:
                _log.info(f"Getting new access token {self.admin!r} using password grant.")
                data = {
                    "client_id": "admin-cli",
                    "grant_type": "password",
                    "username": self.admin,
                    "password": self.password,
                }
            resp = requests.post(
                self._get_url("/realms/master/protocol/openid-connect/token"),
                data=data,
            )
            resp.raise_for_status()
            token_data = resp.json()
            self._tokens = _Tokens(
                expiry=now + token_data["expires_in"],
                refresh_expiry=now + token_data["refresh_expires_in"],
                token_data=token_data,
            )
        return self._tokens.token_data["access_token"]

    def _get_auth_headers(self) -> dict:
        # TODO: cache/reuse access token
        access_token = self._get_access_token()
        return {
            "Authorization": f"Bearer {access_token}",
        }

    def request(self, method: str, path: str, *args, **kwargs):
        url = self._get_url(path)
        _log.info(f"Doing {method} {url}")
        resp = requests.request(
            method=method,
            url=url,
            *args,
            headers=self._get_auth_headers(),
            **kwargs,
        )
        resp.raise_for_status()
        return resp

    def get(self, path: str, *args, **kwargs):
        return self.request(method="GET", path=path, *args, **kwargs)

    def post(self, path: str, *args, **kwargs):
        return self.request(method="POST", path=path, *args, **kwargs)

    def get_realms(self) -> Set[str]:
        return set(r["realm"] for r in self.get("/admin/realms").json())

    def create_realm(self, realm: Optional[str] = None) -> KcResource:
        realm = realm or random_name(prefix="realm-", length=8)
        resp = self.post(
            "/admin/realms",
            json={"realm": realm, "enabled": True},
        )
        location = resp.headers["Location"]
        info = self.get(location).json()
        return KcResource(type="realm", id=info["id"], name=info["realm"], info=info)

    def set_default_realm(self, realm: str):
        assert realm in self.get_realms()
        self.default_realm = realm

    def create_client(
        self,
        client_id: Optional[str] = None,
        *,
        realm: Optional[str] = None,
        public=False,
        standard_flow=True,
        service_account=True,
        password_flow=True,
        device_flow=True,
    ) -> KcResource:
        client_id = client_id or random_name(prefix="client-", length=8)
        realm = realm or self.default_realm
        settings = {
            "protocol": "openid-connect",
            "clientId": client_id,
            "enabled": True,
            # Non-public: "confidential" client with secret.
            "publicClient": public,
            # Authorization Code Flow
            "standardFlowEnabled": standard_flow,
            # Service accounts: Client Credentials Grant.
            "serviceAccountsEnabled": service_account,
            # Direct Access: Resource Owner Password Credentials Grant.
            "directAccessGrantsEnabled": password_flow,
            "attributes": {
                # Device authorization grant, aka "device flow".
                "oauth2.device.authorization.grant.enabled": device_flow,
            },
        }
        _log.info(f"Creating client {client_id!r} in realm {realm!r}")
        resp = self.post(f"/admin/realms/{realm}/clients", json=settings)
        location = resp.headers["Location"]
        info = self.get(location).json()
        return KcResource(type="client", id=info["id"], name=info["clientId"], info=info)

    def create_user(
        self,
        username: Optional[str] = None,
        *,
        password: Optional[str] = None,
        realm: Optional[str] = None,
    ) -> KcResource:
        username = username or random_name(prefix="user-", length=8)
        password = password or random_name(prefix="pwd-", length=4)
        realm = realm or self.default_realm
        settings = {
            "username": username,
            "enabled": True,
            "credentials": [
                {
                    "type": "password",
                    "value": password,
                    "temporary": False,
                }
            ],
        }
        _log.info(f"Creating user {username!r} in realm {realm!r}")
        resp = self.post(f"/admin/realms/{realm}/users", json=settings)
        location = resp.headers["Location"]
        info = self.get(location).json()
        return KcResource(type="user", id=info["id"], name=info["username"], info=info)


if __name__ == "__main__":
    """
    First, run dummy Keycloak instance, e.g. like this:

        docker run --rm \
            -p 8642:8080 \
            -e KEYCLOAK_ADMIN=admin \
            -e KEYCLOAK_ADMIN_PASSWORD=admin \
            quay.io/keycloak/keycloak:21.0.2 start-dev
    """
    enable_logging()
    nanny = KeycloakNanny("http://localhost:8642")

    realm = nanny.create_realm("playground")
    print("Created realm", realm)
    nanny.set_default_realm(realm.name)

    client = nanny.create_client()
    print("Created client", client)

    user = nanny.create_user()
    print("Created user", user)
