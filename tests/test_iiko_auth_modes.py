from __future__ import annotations

import hashlib
import unittest
from urllib.parse import parse_qs

import httpx

from app.iiko.auth import build_auth_candidates, extract_auth_result
from app.iiko.server_client import IikoServerClient


class IikoAuthHelpersTests(unittest.TestCase):
    def test_build_auth_candidates_auto_contains_json_and_sha1_form_pass(self) -> None:
        candidates = build_auth_candidates(username="user", password="secret", mode="auto")
        names = [candidate.name for candidate in candidates]
        self.assertIn("json_login_password", names)
        self.assertIn("form_login_password", names)
        self.assertIn("form_login_pass_sha1", names)

    def test_extract_auth_result_reads_plain_text_token(self) -> None:
        request = httpx.Request("POST", "https://example/resto/api/auth")
        response = httpx.Response(200, text="abcde-12345-token", request=request)
        result = extract_auth_result(response)
        self.assertEqual(result.key_token, "abcde-12345-token")
        self.assertEqual(result.token_source, "plain_text")


class IikoServerClientAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_fallback_reaches_form_pass_sha1(self) -> None:
        username = "user"
        password = "user#test"
        sha1_password = hashlib.sha1(password.encode("utf-8")).hexdigest()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path != "/resto/api/auth":
                return httpx.Response(404, request=request)

            content_type = request.headers.get("content-type", "")
            if content_type.startswith("application/json"):
                return httpx.Response(
                    500,
                    text=(
                        "The @FormParam is utilized when the content type of the request entity "
                        "is not application/x-www-form-urlencoded"
                    ),
                    request=request,
                )

            payload = parse_qs(request.content.decode("utf-8"))
            login = payload.get("login", [""])[0]
            passwd = payload.get("pass", [""])[0]
            if login == username and passwd == sha1_password:
                return httpx.Response(200, text="token-from-sha1", request=request)

            return httpx.Response(401, text="Неверный пароль для пользователя 'user'", request=request)

        client = IikoServerClient(base_url="https://example.local")
        transport = httpx.MockTransport(handler)

        async with httpx.AsyncClient(base_url="https://example.local", transport=transport) as async_client:
            headers, key_token = await client._auth(async_client, username=username, password=password)

        self.assertEqual(key_token, "token-from-sha1")
        self.assertEqual(headers.get("Authorization"), "Bearer token-from-sha1")


if __name__ == "__main__":
    unittest.main()
