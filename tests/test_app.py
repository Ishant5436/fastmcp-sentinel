"""Web app (app/index.html): pinned ABI constants and a real-browser flow against anvil."""

from __future__ import annotations

import functools
import http.server
import json
import re
import threading
from pathlib import Path

import pytest

from conftest import MOCK_ARTIFACT, VAULT_ARTIFACT, abi_word
from fastmcp_sentinel.vault import PAYMENT_EVENT_TOPIC, VaultStatus

APP_DIR = Path(__file__).resolve().parent.parent / "app"
HTML = (APP_DIR / "index.html").read_text(encoding="utf-8")


def _app_selectors() -> dict[str, str]:
    block = re.search(r"const SEL = \{(.*?)\};", HTML, re.S).group(1)
    return dict(re.findall(r"(\w+):\s*\"([0-9a-f]{8})\"", block))


def test_app_constants_match_python_client():
    assert f'const PAYMENT_TOPIC = "{PAYMENT_EVENT_TOPIC}"' in HTML
    statuses = re.search(r"const STATUS = \[(.*?)\];", HTML).group(1)
    assert re.findall(r'"(\w+)"', statuses) == [s.name for s in VaultStatus]


@pytest.mark.skipif(not VAULT_ARTIFACT.exists(), reason="contracts not built")
def test_app_selectors_match_artifact():
    ids = json.loads(VAULT_ARTIFACT.read_text())["methodIdentifiers"]
    sigs = {
        "policy": "policy()",
        "check": "check(address,uint256)",
        "pay": "pay(address,uint256,bytes32)",
        "pause": "pause()",
        "unpause": "unpause()",
        "withdraw": "withdraw(address,uint256)",
    }
    sel = _app_selectors()
    for key, sig in sigs.items():
        assert sel[key] == ids[sig], key
    assert sel["transfer"] == "a9059cbb"


# --- real browser ----------------------------------------------------------------

PROVIDER = """
window.ethereum = {
  _listeners: {},
  on(evt, fn) { this._listeners[evt] = fn; },
  async request({ method, params }) {
    if (method === "eth_requestAccounts" || method === "eth_accounts") return [window.__ACCOUNT];
    if (method === "wallet_switchEthereumChain" || method === "wallet_addEthereumChain") return null;
    const res = await fetch(window.__RPC, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params: params || [] }) });
    const body = await res.json();
    if (body.error) throw Object.assign(new Error(body.error.message), { code: body.error.code });
    return body.result;
  },
};
"""


@pytest.fixture
def app_url():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(APP_DIR))

    class Quiet(handler.func):  # type: ignore[name-defined]
        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(APP_DIR)))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    httpd.shutdown()


def test_app_deposit_and_pay_in_browser(anvil, deployed, app_url):
    sync_api = pytest.importorskip("playwright.sync_api")
    agent, token, vault = deployed["agent"], deployed["token"], deployed["vault"]
    merchant = "0x000000000000000000000000000000000000c0de"

    mock = json.loads(MOCK_ARTIFACT.read_text())
    mint = "0x" + mock["methodIdentifiers"]["mint(address,uint256)"] + abi_word(agent) + abi_word(20_000_000)
    anvil.send(deployed["owner"], mint, to=token)

    try:
        pw = sync_api.sync_playwright().start()
        browser = pw.chromium.launch()
    except Exception as err:  # browser not installed
        pytest.skip(f"chromium unavailable: {err}")
    try:
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(f"window.__RPC = {json.dumps(anvil.url)}; window.__ACCOUNT = {json.dumps(agent)};")
        page.add_init_script(PROVIDER)
        page.goto(f"{app_url}?chain=31337&rpc={anvil.url}&vault={vault}")

        page.wait_for_selector("#dashboard:not([hidden])")
        assert page.text_content("#s-balance") == "100.00"
        assert page.text_content("#d-agent").lower() == agent.lower()

        page.click("#connect")
        page.wait_for_function("!document.getElementById('pay').disabled")
        assert page.is_disabled("#pause"), "agent must not get owner controls"

        page.fill("#deposit-amount", "5")
        page.click("#deposit")
        page.wait_for_function("document.getElementById('s-balance').textContent === '105.00'")

        page.fill("#pay-to", merchant)
        page.fill("#pay-amount", "2.5")
        page.fill("#pay-memo", "invoice-9")
        page.click("#pay")
        page.wait_for_function("document.getElementById('s-spent').textContent === '2.50'")
        page.wait_for_selector("#payments td:has-text('invoice-9')")
        assert "Payment: confirmed" in page.text_content("#log")

        page.fill("#pay-amount", "11")
        page.click("#check")
        page.wait_for_function("document.getElementById('log').textContent.includes('EXCEEDS_SINGLE_LIMIT')")
        assert errors == []
    finally:
        browser.close()
        pw.stop()

    balance = int(anvil.rpc("eth_call", [{"to": token, "data": "0x70a08231" + abi_word(merchant)}, "latest"]), 16)
    assert balance == 2_500_000
