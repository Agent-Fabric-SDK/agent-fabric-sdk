# Governed error taxonomy

The proxy doesn't just pass model calls through — it enforces policy. When it
rejects a call, the SDK turns the response into a **typed exception** so you
branch on the governance outcome instead of parsing bodies.

## The rejection shapes `classify()` types

`classify()` types six rejection shapes. **Four are live-verified** against the
sandbox proxy (auth, PII, token rate limit, upstream); **injection** is typed by
its header discriminator but its body is pending live capture, and
**content-moderation** deliberately falls through — both tracked in [#253] for
sandbox confirmation. The critical lesson: **neither the status code nor the
shape of the `error` value alone is a sufficient discriminator** — a `403` can be
PII (a policy block) *or* auth, and the same nested-object envelope is emitted by
both the upstream provider and a gateway policy. The authoritative discriminator
is the error **`type`** plus specific headers.

| Rejection | HTTP | Discriminator | Maps to | Verified? |
|---|---|---|---|---|
| Client-ID enforcement (auth) | `401` | flat `{"error":"…"}` + `www-authenticate: Client-ID-Enforcement` | `AuthError` | live |
| PII detected | `403` | nested `{"error":{type:"pii_detected"}}`, **no** `www-authenticate` | `PIIDetected` (parses `entities`) | live |
| Injection protection | `400` | header `x-injection-protection: blocked` (**not** the status) | `PromptInjectionBlocked` | pending (#253) |
| Token rate limit | `429` | **empty body**; `x-token-limit`/`-remaining`/`-reset` headers (ms) | `TokenBudgetExceeded` (`retry_after` derived) | live |
| Content moderation / guardrails | `4xx` | falls through — no nested `error`, no injection header | generic `PolicyViolation` | pending (#253) |
| Upstream provider 4xx | `4xx` | nested `error` object **with** `code`/`type`/`param` | `UpstreamRequestError` | live |
| Upstream 5xx | `5xx` | status range (no competing discriminator) | `UpstreamModelError` (retryable) | live |

`PIIDetected` is checked **before** the generic 401/403→auth rule, precisely
because a PII block is a `403` that is *not* an auth failure. Likewise the
injection check gates on the `x-injection-protection` header, so an ordinary
malformed `400` stays an ordinary refusal.

Client-ID enforcement (`401`) is a **consumer-auth** case, not one of the six
policy-rejection rows.

[#253]: https://github.com/Donkey-Development-Kit/donkey-development-kit/issues/253

## The exception tree

All importable from `donkey_kit`:

```
DonkeyError                     # base of the whole tree
├─ ConfigError                  # misconfiguration (raised locally, pre-flight)
├─ AuthError                    # 401 — bad/missing consumer credentials
├─ PolicyViolation              # base for every governance rejection
│  ├─ PIIDetected               # 403, type=pii_detected; .entities
│  ├─ TokenBudgetExceeded       # 429; .retry_after (seconds)
│  ├─ PromptInjectionBlocked    # x-injection-protection: blocked (body pending #253)
│  └─ ContentSafetyBlocked      # (shape not yet captured — falls through today)
├─ UpstreamRequestError         # upstream 4xx; .code/.error_type/.param
└─ UpstreamModelError           # upstream 5xx — provider error, retryable
```

## The ids every `DonkeyError` carries

Every exception in the tree carries three ids so you can join a failure to your
logs and to the gateway's own record — **three ids, three provenances**:

| Attribute | What it is | Provenance |
| --- | --- | --- |
| `.correlation_id` | The **run** id, shared by every call in a [`donkey.run()`](https://donkey-development-kit.github.io/donkey-development-kit/concepts/observability.md#grouping-a-run-the-run-id-on-the-span-the-call-id-on-the-error) block | The `X-Correlation-Id` request header the client sent — always equals what went on the wire. |
| `.call_id` | The **per-call** id, unique per logical request and stable across that request's retries | The `X-Donkey-Request-Id` request header the client sent. Present **even when the request fails before any response** (a transport error). |
| `.request_id` | The **gateway's own** id | Read back from the `x-request-id` **response** header. Absent on a transport error, since there is no response. |

`classify(response)` fills `.correlation_id` and `.call_id` from the response's
own request, so bridging an `openai` error (below) needs no extra wiring — the
correlation id on the exception equals the header that was actually sent. (If you
overrode the header names in config, pass the ids to `classify()` explicitly.)

## Bridging from the raw client

  `donkey.llm.client()` is the **OpenAI SDK**, so on an HTTP failure it raises
  `openai.APIStatusError`, **not** a `DonkeyError`. Bridge into the taxonomy by
  applying `classify()` to the error's `.response`.

```python
import openai
from donkey_kit import PIIDetected, TokenBudgetExceeded, AuthError
from donkey_kit.core.errors import classify

try:
    resp = await client.chat.completions.create(model="gpt-4o", messages=msgs)
except openai.APIStatusError as e:
    governed = classify(e.response)          # -> a DonkeyError subclass
    if isinstance(governed, PIIDetected):
        print("blocked, entities:", governed.entities)
    elif isinstance(governed, TokenBudgetExceeded):
        print("slow down; retry after", governed.retry_after, "s")
    elif isinstance(governed, AuthError):
        print("bad credentials:", governed)
    else:
        print(f"{type(governed).__name__}: {governed}")
except openai.APIConnectionError as e:
    print("could not reach the proxy:", e)
```

The blocking client from `donkey.llm.client(sync=True)` behaves identically here
— drop the `await`. It is the same OpenAI SDK raising the same
`openai.APIStatusError`, and `classify()` reads the response the same way, so the
taxonomy is not an async-only feature.

One deliberate difference sits below the taxonomy, in the retry policy. Both
clients retry only transient upstream/gateway failures (502/503/504) and treat
every 4xx as terminal — **including a 429**: on this proxy a 429 is a
token-budget refusal (`TokenBudgetExceeded`), so retrying it would only burn the
same already-exhausted window. `retry_after` is still surfaced for you to pace
against, but the transport never silently retries it. The async client
additionally refreshes its token and retries **once** on a 401, because it may
carry an Anypoint control-plane credential. The blocking client holds no such
credential — that refresh protocol is async-only — so a 401 there is terminal and
surfaces immediately as `AuthError`.

## Not-yet-captured shapes

Prompt-injection and content-safety rejection **bodies** are not yet captured, so
today they fall through to a generic `PolicyViolation` rather than their specific
type. This is deliberate (§0.3) — we don't invent a discriminator we haven't
observed. See [Verification policy](https://donkey-development-kit.github.io/donkey-development-kit/concepts/verification.md).
