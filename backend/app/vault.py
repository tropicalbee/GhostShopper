"""One-time buyer setup for agent payments: save the sandbox buyer's PayPal account with the Vault API.

    python -m backend.app.vault setup              # prints a link; log in once as the sandbox buyer and approve
    python -m backend.app.vault finish <setup_id>  # exchanges the approved setup token for a payment token

After that the shopper agent can pay with `--payment vault`: no popup, no password. The payment token is stored in
SQLite (table vault_tokens) and is never sent to the LLM or written to run logs.

Docs: https://developer.paypal.com/docs/checkout/save-payment-methods/purchase-later/js-sdk/paypal/
      https://developer.paypal.com/docs/api/payment-tokens/v3/
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from . import db
from .config import Settings, get_settings
from .paypal import PayPalClient, PayPalError
from .paypal_mock import FakePayPalClient


class VaultError(ValueError):
    pass


def make_client(settings: Settings) -> PayPalClient | FakePayPalClient:
    if settings.paypal_mode == "mock":
        return FakePayPalClient()
    if not settings.paypal_configured:
        raise VaultError("Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env (sandbox REST app).")
    return PayPalClient(settings.paypal_client_id, settings.paypal_client_secret)


def _describe(exc: PayPalError) -> str:
    hint = ""
    if exc.status_code in (401, 403) or exc.issue in ("PERMISSION_DENIED", "NOT_AUTHORIZED"):
        hint = (" Enable the Vault / 'Save payment methods' feature on your sandbox REST app in the "
                "developer dashboard (Apps & Credentials > your app > Features).")
    return f"PayPal refused the request: {exc} (debug_id={exc.debug_id}).{hint}"


async def setup_token(settings: Settings, client: Any) -> dict[str, Any]:
    base = settings.app_base_url
    try:
        return await client.create_setup_token(f"{base}/api/paypal/vault/return", f"{base}/api/paypal/vault/cancel")
    except PayPalError as exc:
        raise VaultError(_describe(exc)) from exc


def approve_link(setup: dict[str, Any]) -> str:
    for link in setup.get("links") or []:
        if link.get("rel") in ("approve", "payer-action"):
            return link["href"]
    raise VaultError("PayPal returned no approve link for the setup token.")


async def finish_setup(settings: Settings, client: Any, setup_token_id: str) -> dict[str, Any]:
    try:
        token = await client.create_payment_token(setup_token_id)
    except PayPalError as exc:
        raise VaultError(_describe(exc)) from exc
    db.init_db(settings.database_path)
    customer_id = (token.get("customer") or {}).get("id")
    db.save_vault_token(settings.database_path, paypal_mode=settings.paypal_mode,
                        payment_token_id=token["id"], customer_id=customer_id)
    return {"customer_id": customer_id, "paypal_mode": settings.paypal_mode}


def load_token(db_path: Path, paypal_mode: str) -> dict[str, Any]:
    """The saved token for this mode, or an explicit error telling the user how to create one."""
    row = db.latest_vault_token(db_path, paypal_mode)
    if row is None:
        raise VaultError(f"No saved PayPal payment token for PAYPAL_MODE={paypal_mode}. "
                         "Run `python -m backend.app.vault setup` once, approve it as the sandbox buyer, "
                         "then `python -m backend.app.vault finish <setup_token_id>`.")
    return row


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m backend.app.vault")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="start the one-time buyer approval")
    f = sub.add_parser("finish", help="save the payment token after the buyer approved")
    f.add_argument("setup_token_id")
    a = p.parse_args()
    settings = get_settings()

    async def go() -> None:
        client = make_client(settings)
        try:
            if a.cmd == "setup":
                setup = await setup_token(settings, client)
                print(f"Setup token: {setup['id']}")
                print(f"Open this link, log in as the SANDBOX BUYER (personal account) and approve:\n  {approve_link(setup)}")
                if settings.paypal_mode == "mock":
                    print("PAYPAL_MODE=mock: nothing to approve. Go straight to the next step.")
                print(f"Then run:\n  python -m backend.app.vault finish {setup['id']}")
            else:
                done = await finish_setup(settings, client, a.setup_token_id)
                print(f"Saved the {done['paypal_mode']} payment token (customer {done['customer_id']}). "
                      "Agent payments: python -m backend.app.agent --checkout --payment vault ...")
        finally:
            await client.aclose()

    try:
        asyncio.run(go())
    except VaultError as exc:
        print(f"Vault error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
