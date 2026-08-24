import unittest
from tools.gateway.adapters import adapt_sse_payload
from tools.gateway.metrics import RequestMetrics

class GatewayTests(unittest.TestCase):
    def test_passthrough_preserves_reasoning(self):
        payload = {"choices": [{"delta": {"reasoning_content": "x", "tool_calls": [{"id": "1"}]}}]}
        self.assertEqual(adapt_sse_payload(payload, "passthrough"), payload)

    def test_jetbrains_adds_id_without_stripping_fields(self):
        payload = {"choices": [{"delta": {"reasoning_content": "x"}}]}
        out = adapt_sse_payload(payload, "jetbrains")
        self.assertIn("id", out)
        self.assertEqual(out["choices"][0]["delta"]["reasoning_content"], "x")

    def test_metrics_does_not_call_chunks_tokens(self):
        m = RequestMetrics(); m.record_chunk(); result = m.finish()
        self.assertIsNone(result["tokens_per_s"])
        self.assertGreater(result["chunks_per_s"], 0)

if __name__ == "__main__": unittest.main()
