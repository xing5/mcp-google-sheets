import socket
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import MagicMock, patch

from google_auth_oauthlib.flow import InstalledAppFlow

from mcp_google_sheets import server

CLIENT_FIELDS = {
    "client_id": "test-client.apps.googleusercontent.com",
    "client_secret": "test-secret",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}
BASE = "https://tunnel.example.com"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def oauth_env(host="localhost", port="0", base=""):
    return patch.multiple(server, OAUTH_HOST=host, OAUTH_PORT=port, OAUTH_REDIRECT_BASE=base)


class LoopbackFlowTests(unittest.TestCase):
    def test_defaults_use_random_localhost_port(self):
        flow = MagicMock()
        with oauth_env():
            server._run_oauth_flow(flow)
        flow.run_local_server.assert_called_once_with(host="localhost", port=0)

    def test_fixed_host_and_port(self):
        flow = MagicMock()
        with oauth_env(host="127.0.0.1", port="3500"):
            server._run_oauth_flow(flow)
        flow.run_local_server.assert_called_once_with(host="127.0.0.1", port=3500)


class ConfigValidationTests(unittest.TestCase):
    def assert_rejected(self, **env):
        flow = MagicMock()
        with oauth_env(**env), self.assertRaises(ValueError):
            server._run_oauth_flow(flow)
        flow.run_local_server.assert_not_called()

    def test_rejects_wildcard_hosts(self):
        for host in ("0.0.0.0", "::", "[::]", ""):
            with self.subTest(host=host):
                self.assert_rejected(host=host)

    def test_rejects_bad_ports(self):
        for port in ("abc", "-1", "65536"):
            with self.subTest(port=port):
                self.assert_rejected(port=port)

    def test_redirect_base_requires_fixed_port(self):
        self.assert_rejected(base=BASE)

    def test_redirect_base_must_be_https_without_query(self):
        for base in ("http://tunnel.example.com", "tunnel.example.com", "https://", "https://t.example/?a=1"):
            with self.subTest(base=base):
                self.assert_rejected(port="3500", base=base)

    def test_redirect_uri_trims_trailing_slash_and_keeps_path(self):
        self.assertEqual(server._oauth_redirect_uri(BASE + "/"), BASE + "/oauth2callback")
        self.assertEqual(server._oauth_redirect_uri(BASE + "/sheets"), BASE + "/sheets/oauth2callback")


class RedirectBaseFlowTests(unittest.TestCase):
    """Drives the real callback listener over HTTP; only the token exchange with Google is faked."""

    def start_flow(self, client_type):
        flow = InstalledAppFlow.from_client_config({client_type: CLIENT_FIELDS}, server.SCOPES)
        self.exchanges = []

        def fake_fetch_token(**kwargs):
            self.exchanges.append(kwargs)
            flow.oauth2session.token = {"access_token": "a", "refresh_token": "r", "token_type": "Bearer",
                                     "expires_at": time.time() + 3600}

        flow.fetch_token = fake_fetch_token
        self.port = free_port()
        self.result = {}
        logged = []

        def run():
            with oauth_env(host="127.0.0.1", port=str(self.port), base=BASE), \
                    patch.object(server.logger, "warning", side_effect=lambda *a: logged.append(a)):
                try:
                    self.result["creds"] = server._run_oauth_flow(flow)
                except Exception as e:
                    self.result["error"] = e

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        for _ in range(100):  # wait for the listener to bind
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.1).close()
                break
            except OSError:
                time.sleep(0.02)
        self.assertEqual(len(logged), 1)
        return urllib.parse.urlsplit(logged[0][1])

    def get(self, path):
        try:
            return urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5).status
        except urllib.error.HTTPError as e:
            return e.code

    def test_completes_consent_for_installed_and_web_clients(self):
        for client_type in ("installed", "web"):
            with self.subTest(client_type=client_type):
                auth_url = self.start_flow(client_type)
                params = urllib.parse.parse_qs(auth_url.query)
                self.assertEqual(params["redirect_uri"], [BASE + "/oauth2callback"])
                self.assertEqual(params["access_type"], ["offline"])
                self.assertEqual(params["prompt"], ["consent"])

                self.assertEqual(self.get("/favicon.ico"), 404)
                self.assertEqual(self.get("/oauth2callback?code=abc&state=xyz"), 200)
                self.thread.join(5)

                self.assertEqual(self.exchanges, [
                    {"authorization_response": BASE + "/oauth2callback?code=abc&state=xyz"}])
                self.assertEqual(self.result["creds"].refresh_token, "r")

    def test_denied_consent_raises(self):
        self.start_flow("web")
        self.assertEqual(self.get("/oauth2callback?error=access_denied"), 400)
        self.thread.join(5)
        self.assertIsInstance(self.result["error"], RuntimeError)
        self.assertEqual(self.exchanges, [])


if __name__ == "__main__":
    unittest.main()
