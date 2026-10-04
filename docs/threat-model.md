# Threat model (lab scope)

**System:** agents call an LLM and MCP tools through one gateway on a kind cluster.
**Out of scope for this lab:** agent-to-agent (A2A) traffic, a real identity provider, TLS on the listener, multi-cluster.

## Inventory (Identify)

| Asset | Where | Owner | Sensitivity |
|---|---|---|---|
| agentgateway proxy and controller | `agentgateway-system` | platform | High: every call passes through it |
| LLM provider key | Secret `llm-provider-key` | platform | High |
| Token signing key | `keys/private.pem` on the laptop | identity | High |
| MCP server `everything` | `agentic-lab` | tools team | Medium: `get-env` exposes its environment |
| Mock LLM | `agentic-lab` | platform | Low |
| Agent identities | `orchestrator`, `worker` (JWT `sub`) | agent owners | Medium |

## Threats and controls

| # | Path | Threat | Control | CSF function | Proof (check.py) |
|---|---|---|---|---|---|
| T1 | Agent to LLM | Anonymous or expired caller uses the model | JWT authentication on the Gateway | Protect | 1, 2 |
| T2 | Agent to LLM | Provider key copied into every agent | Key held in a Secret, injected by the gateway | Protect | 3 (see mock-llm log) |
| T3 | Agent to LLM | Secret or card number sent in a prompt | Prompt guard, request side, reject | Protect | 4 |
| T4 | Agent to LLM | Sensitive data returned by the model | Prompt guard, response side, mask | Protect | 5 |
| T5 | Agent to tools | Agent discovers and calls tools it has no need for | Per-identity tool rules (CEL) | Protect | 6, 7 |
| T6 | Agent to tools | Dangerous tool exposed to everyone (`get-env`) | Tool not allowed for any identity | Protect | 8 |
| T7 | Agent to tools | Anonymous MCP session | JWT authentication on the Gateway | Protect | 10 |
| T8 | Agent to LLM | Runaway agent loop exhausts the budget | Rate limit keyed on agent identity | Protect | 11 |
| T9 | All | Nobody notices any of the above | Access logs with identity and tool name, metrics | Detect | Step 5 |
| T10 | All | Compromised agent keeps working | Deny policy for that identity; key rotation | Respond | Step 6 |
| T11 | All | Cluster or config lost or tampered with | Everything in Git; rebuild from scratch | Recover | Step 7 |

## Known gaps (be honest about these in the write-up)

- Pods can still reach the MCP server and mock LLM directly, bypassing the gateway, unless a NetworkPolicy forbids it.
- Tokens are minted by a script, not an identity provider; there is no per-token revocation, only key rotation or a deny rule.
- The prompt guards are regular expressions: they catch known patterns, not paraphrased or encoded secrets.
- The listener is plain HTTP.
