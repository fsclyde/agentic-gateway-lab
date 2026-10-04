"""Tiny OpenAI-compatible stand-in so the lab needs no API key and no GPU."""
import json, time
from http.server import BaseHTTPRequestHandler, HTTPServer

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        last = (body.get("messages") or [{}])[-1].get("content", "")
        if "leak" in str(last).lower():
            text = "Sure, the admin contact is admin@example.com and the key is AKIAIOSFODNN7EXAMPLE."
        else:
            text = f"mock-llm reply to: {last}"
        out = {"id": "chatcmpl-mock", "object": "chat.completion", "created": int(time.time()),
               "model": body.get("model", "mock"),
               "choices": [{"index": 0, "finish_reason": "stop",
                            "message": {"role": "assistant", "content": text}}],
               "usage": {"prompt_tokens": 12, "completion_tokens": 9, "total_tokens": 21}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a):
        print("mock-llm", self.command, self.path, "auth=" + str(self.headers.get("authorization")), flush=True)

HTTPServer(("0.0.0.0", 8000), H).serve_forever()
