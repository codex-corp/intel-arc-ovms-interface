import unittest

import proxy_server


class GatewayContractTests(unittest.TestCase):
    def setUp(self):
        self._strip_reasoning = proxy_server.STRIP_REASONING
        self._inject_stream_id = proxy_server.INJECT_STREAM_ID

    def tearDown(self):
        proxy_server.STRIP_REASONING = self._strip_reasoning
        proxy_server.INJECT_STREAM_ID = self._inject_stream_id

    def test_passthrough_preserves_reasoning_and_tool_calls(self):
        proxy_server.STRIP_REASONING = False
        proxy_server.INJECT_STREAM_ID = True
        payload = {
            "choices": [
                {
                    "delta": {
                        "reasoning_content": "thinking",
                        "tool_calls": [{"id": "call-1"}],
                        "content": "answer",
                    }
                }
            ]
        }

        result = proxy_server._adapt_openai_payload(payload, request_id="generated-id")

        self.assertEqual("generated-id", result["id"])
        delta = result["choices"][0]["delta"]
        self.assertEqual("thinking", delta["reasoning_content"])
        self.assertEqual([{"id": "call-1"}], delta["tool_calls"])
        self.assertEqual("answer", delta["content"])

    def test_existing_stream_id_is_not_replaced(self):
        proxy_server.INJECT_STREAM_ID = True
        payload = {"id": "upstream-id", "choices": []}

        result = proxy_server._adapt_openai_payload(payload, request_id="generated-id")

        self.assertEqual("upstream-id", result["id"])

    def test_legacy_reasoning_strip_is_opt_in(self):
        proxy_server.STRIP_REASONING = True
        payload = {
            "choices": [
                {
                    "delta": {
                        "reasoning_content": "thinking",
                        "tool_calls": [{"id": "call-1"}],
                    },
                    "message": {
                        "reasoning_content": "final reasoning",
                        "content": "answer",
                    },
                }
            ]
        }

        result = proxy_server._adapt_openai_payload(payload)

        self.assertNotIn("reasoning_content", result["choices"][0]["delta"])
        self.assertNotIn("reasoning_content", result["choices"][0]["message"])
        self.assertEqual([{"id": "call-1"}], result["choices"][0]["delta"]["tool_calls"])

    def test_completion_tokens_are_taken_only_from_valid_usage(self):
        self.assertEqual(
            42,
            proxy_server._completion_tokens_from_usage(
                {"usage": {"completion_tokens": 42}}
            ),
        )
        self.assertIsNone(proxy_server._completion_tokens_from_usage({"usage": {}}))
        self.assertIsNone(
            proxy_server._completion_tokens_from_usage(
                {"usage": {"completion_tokens": "42"}}
            )
        )

    def test_meaningful_delta_includes_reasoning_and_tools(self):
        self.assertTrue(
            proxy_server._has_meaningful_delta(
                {"choices": [{"delta": {"reasoning_content": "thinking"}}]}
            )
        )
        self.assertTrue(
            proxy_server._has_meaningful_delta(
                {"choices": [{"delta": {"tool_calls": [{"id": "call-1"}]}}]}
            )
        )
        self.assertFalse(
            proxy_server._has_meaningful_delta(
                {"choices": [{"delta": {"content": ""}}]}
            )
        )

    def test_boolean_config_parser(self):
        self.assertTrue(proxy_server._config_bool({"FLAG": "yes"}, "FLAG"))
        self.assertTrue(proxy_server._config_bool({"FLAG": "1"}, "FLAG"))
        self.assertFalse(proxy_server._config_bool({"FLAG": "off"}, "FLAG", True))
        self.assertTrue(proxy_server._config_bool({}, "FLAG", True))


if __name__ == "__main__":
    unittest.main()
