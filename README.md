# Agentic gateway lab

A hands-on lab: put agentgateway in front of an LLM and an MCP tool server on a
local kind cluster, then walk the six NIST CSF 2.0 functions
(Govern, Identify, Protect, Detect, Respond, Recover).

Follow the step-by-step guide in Notion ("Lab guide - agentgateway on a kind cluster").

```
manifests/   Kubernetes manifests, applied in numeric order
  00, 01     namespace and Gateway
  10 - 12    workloads, backends, routes          ("before": no security policy)
  20 - 23    identity, tool rules, guardrails, rate limit   ("after")
  30         incident response: block one agent
scripts/
  tokens.py  create a signing key, mint agent tokens, generate the JWT policy
  check.py   proof script: 11 attack checks, --stage before | after
  mock_llm.py  the stand-in LLM (also embedded in manifests/10-mock-llm.yaml)
docs/
  threat-model.md
```

Versions: agentgateway v1.6.0, Gateway API v1.6.2, @modelcontextprotocol/server-everything 2026.8.31.

Personal learning project. No warranty.
