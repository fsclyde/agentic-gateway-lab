# Agentic gateway lab

A hands-on lab: put [agentgateway](https://agentgateway.dev) in front of an LLM and an
MCP tool server on a local kind cluster, then walk the six NIST CSF 2.0 functions
(Govern, Identify, Protect, Detect, Respond, Recover). A script proves each control
with eleven checks, run before and after the policies are applied.

- Write-up: https://agenticcyber.dev/projects/agentic-gateway
- Step-by-step guide with explanations: https://agenticcyber.dev/projects/agentic-gateway/lab

Versions: agentgateway v1.6.0 · Gateway API v1.6.2 · @modelcontextprotocol/server-everything 2026.8.31

## What you get

```
laptop (check.py, tokens.py) --port-forward--> agentgateway-proxy --> mock-llm
                                                      |              (OpenAI-compatible)
                                                      +-----------> MCP server "everything"
                                                                     echo, get-sum, get-env
```

Two agent identities, `orchestrator` and `worker`, are JWTs you mint locally.
The gateway checks the token, decides which tools each agent may use, inspects
prompts and answers, limits the request rate and logs every call.

## Requirements

Docker (Docker Desktop, OrbStack or Colima), `kind`, `kubectl`, `helm`, Python 3.9+.

```bash
brew install kind kubectl helm        # macOS
```

## Quickstart

About 15 minutes. Run everything from the root of this repository.

```bash
# 0. Python environment (repeat `source venv/bin/activate` in every new terminal)
python3 -m venv venv && source venv/bin/activate
pip install PyJWT cryptography

# 1. Cluster, Gateway API, agentgateway
kind create cluster --name agentic

kubectl apply --server-side \
  -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.2/standard-install.yaml

helm upgrade -i agentgateway-crds oci://cr.agentgateway.dev/charts/agentgateway-crds \
  --create-namespace --namespace agentgateway-system --version v1.6.0

helm upgrade -i agentgateway oci://cr.agentgateway.dev/charts/agentgateway \
  --namespace agentgateway-system --version v1.6.0 --wait --timeout 5m

# 2. Gateway, workloads, routes (no security policy yet)
kubectl apply -f manifests/00-namespace.yaml -f manifests/01-gateway.yaml
kubectl wait --for=condition=Programmed gateway/agentgateway-proxy \
  -n agentgateway-system --timeout 5m

kubectl apply -f manifests/10-mock-llm.yaml -f manifests/11-mcp-server.yaml \
  -f manifests/12-backends-routes.yaml
kubectl rollout status deploy/mock-llm deploy/mcp-everything -n agentic-lab --timeout 5m
```

In a **second terminal**, leave this running:

```bash
kubectl port-forward -n agentgateway-system service/agentgateway-proxy 8080:80
```

Back in the first terminal:

```bash
# 3. Signing key, then attack the unprotected gateway
python3 scripts/tokens.py init
python3 scripts/check.py --stage before      # 11/11: everything is open

# 4. Apply the controls
python3 scripts/tokens.py policy > manifests/20-jwt-policy.yaml
kubectl apply -f manifests/20-jwt-policy.yaml      # agent identity (JWT)
kubectl apply -f manifests/21-mcp-tool-rules.yaml  # which agent may use which tool
kubectl apply -f manifests/22-llm-guardrails.yaml  # inspect prompts and answers
kubectl apply -f manifests/23-llm-rate-limit.yaml  # budget per agent

# 5. Prove it
python3 scripts/check.py                     # 11/11: everything is enforced
```

If you run `check.py` twice within a minute, a check can fail with HTTP 429:
the rate limit from step 4 is still counting. Wait 60 seconds.

### What the checks cover

| # | Check | Before | After |
|---|---|---|---|
| 1 | Caller with no identity reaches the LLM | allowed | 401 |
| 2 | Expired token | allowed | 401 |
| 3 | Orchestrator with a valid token reaches the LLM | allowed | allowed |
| 4 | Prompt containing an AWS key | reaches the model | 403 |
| 5 | Model answer containing an email and a key | returned as is | masked |
| 6 | Tools each agent can see | all 13 | orchestrator 2, worker 1 |
| 7 | Worker calls a tool reserved for the orchestrator | allowed | blocked |
| 8 | Any agent dumps the tool server's environment | password exposed | blocked |
| 9 | Orchestrator calls its own tool | allowed | allowed |
| 10 | Caller with no identity opens an MCP session | allowed | 401 |
| 11 | Worker loops eight LLM calls | all served | throttled after 5 |

### Detect, respond, recover

```bash
# Detect: who was refused, and which tools were called
kubectl logs -n agentgateway-system deploy/agentgateway-proxy --tail=200 | grep -E '401|403|429'
kubectl logs -n agentgateway-system deploy/agentgateway-proxy --tail=200 | grep 'tools/call'

# Respond: block one compromised agent, then rotate the signing key
kubectl apply -f manifests/30-respond-block-worker.yaml
python3 scripts/tokens.py init
python3 scripts/tokens.py policy > manifests/20-jwt-policy.yaml
kubectl apply -f manifests/20-jwt-policy.yaml
kubectl delete -f manifests/30-respond-block-worker.yaml

# Recover: rebuild from this repository and prove the controls are back
kind delete cluster --name agentic
# repeat steps 1, 2 and 4 (skip the tokens.py policy line to keep the same key), then:
python3 scripts/check.py
```

### Clean up

```bash
kind delete cluster --name agentic
deactivate && rm -rf venv keys
```

## Repository layout

```
manifests/   Kubernetes manifests, applied in numeric order
  00, 01     namespace and Gateway
  10 - 12    workloads, backends, routes                     ("before": no security policy)
  20 - 23    identity, tool rules, guardrails, rate limit    ("after")
  30         incident response: block one agent
scripts/
  tokens.py    create a signing key, mint agent tokens, generate the JWT policy
  check.py     proof script: 11 checks, --stage before | after
  mock_llm.py  the stand-in LLM (also embedded in manifests/10-mock-llm.yaml)
docs/
  threat-model.md
```

`manifests/20-jwt-policy.yaml` is generated by `tokens.py policy`. It contains only
the public half of the signing key. Regenerate it with your own key (step 4) before
applying it; the private key stays in `keys/`, which is ignored by Git.

## Known gaps

- Pods can reach the MCP server and the mock LLM directly, bypassing the gateway, until a NetworkPolicy forbids it.
- Tokens come from a script, not an identity provider such as Keycloak.
- Agent-to-agent (A2A) traffic is not covered.
- The prompt guards are regular expressions; they catch known formats only.
- The listener is plain HTTP.

See `docs/threat-model.md` for the full list of threats and controls.

## Notes

Personal learning project, built in my own time. No warranty. Do not reuse the
mock provider key, the demo password or the token script outside a lab.
