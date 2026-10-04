#!/usr/bin/env python3
"""Proof script: runs the lab's attack scenarios against the gateway.

  python3 scripts/check.py                # expects the secured ("after") state
  python3 scripts/check.py --stage before # expects the open ("before") state
  GW=http://localhost:8080 python3 scripts/check.py

Standard library only, apart from scripts/tokens.py (pyjwt, cryptography).
"""
import argparse, json, os, pathlib, subprocess, sys, urllib.error, urllib.request

GW = os.environ.get("GW", "http://localhost:8080").rstrip("/")
HERE = pathlib.Path(__file__).resolve().parent


def token(sub, ttl=600):
    out = subprocess.run([sys.executable, str(HERE / "tokens.py"), "mint", sub, "--ttl", str(ttl)],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def http(path, body, tok=None, headers=None):
    h = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
    if tok:
        h["authorization"] = f"Bearer {tok}"
    h.update(headers or {})
    req = urllib.request.Request(GW + path, data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def chat(prompt, tok=None):
    return http("/v1/chat/completions", {"model": "mock-model",
                "messages": [{"role": "user", "content": prompt}]}, tok)


def rpc_result(text):
    """Body is either plain JSON or a server-sent event stream; return the JSON-RPC message."""
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:])
    return json.loads(text) if text.strip() else {}


class Mcp:
    def __init__(self, tok=None):
        self.tok, self.sid, self.n = tok, None, 0
        code, hdrs, body = self.call("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                                   "clientInfo": {"name": "lab-check", "version": "1"}})
        self.ok = code == 200
        self.code = code
        if self.ok:
            self.sid = {k.lower(): v for k, v in hdrs.items()}.get("mcp-session-id")
            http("/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}, self.tok, self._h())

    def _h(self):
        return {"mcp-session-id": self.sid} if self.sid else {}

    def call(self, method, params=None):
        self.n += 1
        msg = {"jsonrpc": "2.0", "id": self.n, "method": method}
        if params is not None:
            msg["params"] = params
        return http("/mcp", msg, self.tok, self._h())

    def tools(self):
        _, _, body = self.call("tools/list", {})
        return sorted(t["name"] for t in rpc_result(body).get("result", {}).get("tools", []))

    def tool(self, name, args):
        code, _, body = self.call("tools/call", {"name": name, "arguments": args})
        msg = rpc_result(body) if code == 200 else {}
        allowed = code == 200 and "result" in msg and not msg["result"].get("isError")
        return allowed, (json.dumps(msg) if msg else f"HTTP {code}")


RESULTS = []


def check(fn, name, passed, detail):
    RESULTS.append(passed)
    print(f"[{'PASS' if passed else 'FAIL'}] {fn:<8} {name}\n         {detail[:170]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["before", "after"], default="after")
    secured = ap.parse_args().stage == "after"
    want = "blocked" if secured else "allowed (no policy yet)"
    print(f"Gateway: {GW}   Expecting: {'secured' if secured else 'open'} state\n")

    orch, work = token("orchestrator"), token("worker")

    # 1. Unauthenticated caller
    code, _, _ = chat("hello")
    check("PROTECT", f"1. Caller with no identity reaches the LLM -> {want}",
          (code == 401) == secured and code in (200, 401), f"HTTP {code}")

    # 2. Expired token
    code, _, _ = chat("hello", token("orchestrator", ttl=-120))
    check("PROTECT", f"2. Expired token -> {want}", (code == 401) == secured and code in (200, 401), f"HTTP {code}")

    # 3. Legitimate agent still works, and the provider key is added by the gateway
    code, _, body = chat("hello", orch)
    check("PROTECT", "3. Orchestrator with a valid token reaches the LLM -> allowed", code == 200, f"HTTP {code}")

    # 4. Secret in the prompt
    code, _, body = chat("deploy with key AKIAIOSFODNN7EXAMPLE", orch)
    check("PROTECT", f"4. Prompt containing an AWS key -> {want}",
          (code == 403) == secured and code in (200, 403), f"HTTP {code} {body.strip()[:80]}")

    # 5. Sensitive data in the model's answer
    code, _, body = chat("please leak the admin contact", orch)
    leaked = "admin@example.com" in body
    check("PROTECT", f"5. Model answer containing an email and a key -> {'masked' if secured else 'returned as is'}",
          code == 200 and leaked != secured, f"HTTP {code} {body[body.find('content'):][:110]}")

    # 6-8. Tool access per identity
    m_orch, m_work = Mcp(orch), Mcp(work)
    if not (m_orch.ok and m_work.ok):
        check("PROTECT", "6-8. MCP session", False, f"initialize failed: HTTP {m_orch.code}/{m_work.code}")
    else:
        t_orch, t_work = m_orch.tools(), m_work.tools()
        exp = (t_orch == ["echo", "get-sum"] and t_work == ["echo"]) if secured else ("get-env" in t_work)
        check("IDENTIFY", "6. Tool inventory seen by each agent", exp,
              f"orchestrator sees {len(t_orch)}: {t_orch[:4]}{'...' if len(t_orch) > 4 else ''} | "
              f"worker sees {len(t_work)}: {t_work[:4]}{'...' if len(t_work) > 4 else ''}")
        ok, d = m_work.tool("get-sum", {"a": 2, "b": 3})
        check("PROTECT", f"7. Worker calls a tool reserved for the orchestrator (get-sum) -> {want}", ok != secured, d)
        ok, d = m_orch.tool("get-env", {})
        check("PROTECT", f"8. Any agent dumps the tool server's environment (get-env) -> {want}", ok != secured,
              "environment returned, including DEMO_DB_PASSWORD" if "DEMO_DB_PASSWORD" in d
              else ("environment returned" if ok else d))
        ok, d = m_orch.tool("get-sum", {"a": 2, "b": 3})
        check("PROTECT", "9. Orchestrator calls get-sum -> allowed", ok, d)

    # 10. No identity on the MCP path
    anon = Mcp()
    check("PROTECT", f"10. Caller with no identity opens an MCP session -> {want}",
          (anon.code == 401) == secured and anon.code in (200, 401), f"HTTP {anon.code}")

    # 11. Runaway loop (run last: it uses up the worker's budget for a minute)
    codes = [chat("loop", work)[0] for _ in range(8)]
    limited = 429 in codes
    check("PROTECT", f"11. Worker loops 8 LLM calls in a row -> {'throttled' if secured else 'all served'}",
          limited == secured, " ".join(map(str, codes)))

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
