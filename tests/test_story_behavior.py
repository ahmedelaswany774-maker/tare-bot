"""Exercise production functions without starting rendering or network uploads on import."""
import ast
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "story_youtube_uploader.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))


class NetworkError(Exception):
    pass


class HTTPError(NetworkError):
    pass


def load_function(name, **namespace):
    node = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace[name]


def response(status=200, text="نص التجربة"):
    value = Mock(status_code=status)
    value.raise_for_status.side_effect = HTTPError("sensitive request detail") if status >= 400 else None
    value.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return value


class GeminiBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.requests = SimpleNamespace(
            post=Mock(), exceptions=SimpleNamespace(HTTPError=HTTPError, RequestException=NetworkError)
        )
        self.sleep = Mock()
        self.call = load_function(
            "call_gemini", requests=self.requests, time=SimpleNamespace(sleep=self.sleep),
            GEMINI_KEY="test-key", GEMINI_MODELS=("primary", "fallback"),
        )

    def test_503_retries_then_switches_models(self):
        self.requests.post.side_effect = [response(503), response(503), response()]
        self.assertEqual(self.call("prompt", max_retries=2), "نص التجربة")
        self.sleep.assert_called_once_with(5)
        urls = [call.args[0] for call in self.requests.post.call_args_list]
        self.assertIn("primary:", urls[0])
        self.assertIn("primary:", urls[1])
        self.assertIn("fallback:", urls[2])
        self.assertTrue(all("test-key" not in url for url in urls))
        self.assertEqual(self.requests.post.call_args.kwargs["headers"]["x-goog-api-key"], "test-key")

    def test_empty_success_uses_fallback(self):
        empty = response()
        empty.json.return_value = {"candidates": []}
        self.requests.post.side_effect = [empty, response()]
        self.assertEqual(self.call("prompt"), "نص التجربة")
        self.assertEqual(self.requests.post.call_count, 2)

    def test_auth_failure_stops_without_retry_or_request_details(self):
        self.requests.post.return_value = response(403)
        with self.assertRaisesRegex(RuntimeError, "HTTP 403") as exc:
            self.call("prompt")
        self.assertNotIn("sensitive", str(exc.exception))
        self.assertEqual(self.requests.post.call_count, 1)
        self.sleep.assert_not_called()

    def test_network_failures_are_bounded_and_sanitized(self):
        self.requests.post.side_effect = NetworkError("private-request-value")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(RuntimeError) as exc:
            self.call("prompt", max_retries=2)
        self.assertEqual(self.requests.post.call_count, 4)
        self.assertNotIn("private-request-value", output.getvalue() + str(exc.exception))


class EpisodeBehaviorTests(unittest.TestCase):
    def test_next_skips_published_episodes(self):
        manifest = json.loads((ROOT / "content/series/room_17.json").read_text(encoding="utf-8"))
        manifest["episodes"][0]["published"] = True
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "series.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            load = load_function("load_episode", json=json, Path=Path, SERIES_MANIFEST_PATH=str(path), EPISODE_SELECTOR="next")
            self.assertEqual(load()[1]["episode_number"], 5)
            load = load_function("load_episode", json=json, Path=Path, SERIES_MANIFEST_PATH=str(path), EPISODE_SELECTOR="4")
            with self.assertRaises(ValueError):
                load()

    def test_final_fiction_episode_does_not_promise_another_part(self):
        manifest = json.loads((ROOT / "content/series/room_17.json").read_text(encoding="utf-8"))
        gemini = Mock(return_value="نص الحلقة")
        generate = load_function(
            "generate_story", call_gemini=gemini,
            load_growth_policy=lambda: {"cta": {"never_before_core_hook_seconds": 20}},
        )
        self.assertEqual(generate(manifest, manifest["episodes"][-1]), "نص الحلقة")
        prompt = gemini.call_args.args[0]
        self.assertIn("هذه رواية خيالية", prompt)
        self.assertIn("هذه الحلقة الأخيرة", prompt)
        self.assertNotIn("اترك وعدًا واضحًا بالحلقة التالية", prompt)

    def test_preview_exits_before_any_youtube_credentials_are_read(self):
        index = next(i for i, node in enumerate(TREE.body) if isinstance(node, ast.If)
                     and isinstance(node.test, ast.Name) and node.test.id == "PREVIEW_ONLY")
        remaining = ast.Module(body=TREE.body[index:], type_ignores=[])
        with self.assertRaises(SystemExit) as exc:
            exec(compile(remaining, str(SOURCE), "exec"), {"PREVIEW_ONLY": True})
        self.assertEqual(exc.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
