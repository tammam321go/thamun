# Privacy, data residency and security

Phase 1 feedback: "Since wallet data cannot be transferred across borders, an internally hosted AI
solution is recommended" and "Better authentication and stronger production security would still be
needed". This page lists what is implemented in the code today and what a production deployment still
needs. The two are kept apart on purpose.

## Data residency: nothing has to leave the country

| Component | Where it runs | Sends customer data outside? |
|---|---|---|
| Label model, risk model (LightGBM) | A file of about 300 KB loaded by the API process. CPU only | No |
| Isolation Forest | A file of a few MB loaded by the API process. CPU only | No |
| Rules, bill forecast, spending baseline, savings plan | Plain Python in the API process | No |
| Explanations in Bangla and English | Templates in the code | No |
| Optional language model | Only if configured. Off by default | Refused unless the host is internal |

The decision path uses no external service at all. A wallet provider can run the whole engine on its own
servers in Bangladesh with no outbound internet access.

### The language model switch

`LLM_DATA_RESIDENCY` controls the only component that could call an outside service.

| Value | Behaviour |
|---|---|
| `internal_only` (default) | The model is used only if `LLM_BASE_URL` points at a private network address, `localhost`, or a host listed in `LLM_INTERNAL_HOSTS`. A public API address is ignored and templates are used |
| `allow_external` | A public API may be used. Meant for a demo on synthetic data only |

In production the model would be an open-weight model served inside the provider's data centre (for
example with Ollama or vLLM). The code needs no change for that: it speaks the common chat completions
format and only needs the internal address.

What the language model can receive, when one is enabled: the finished alert text for rewording, and for
"Ask Thamun" a short list of computed totals plus the question. It never receives a transaction list, a
phone number of a recipient, a PIN or an OTP. It never returns a decision. A reworded alert is discarded
unless it contains exactly the same numbers as the template and no link.

## What is stored

| Table | Holds | Does not hold |
|---|---|---|
| `scam_reports` | Reported number, pattern, date, a keyed hash of the reporter | The reporter's name, number or customer id |
| `audit_logs` | Time, event, hashed session, demo customer id, payment type, amount, decision, risk score, reason codes, outcome | The recipient's number or name, OTP, PIN |
| `ux_feedback` | Scenario, decision, language, five answers, optional short comment | Name, number. The session hash is kept only to limit repeat submissions and is never exported |

The prototype uses synthetic customers only. It never asks for a real wallet login, PIN or OTP. The OTP
box accepts any four digits and nothing is sent anywhere.

## Security controls

| Control | Implemented in this repository | Still needed for production |
|---|---|---|
| Authentication | Signed session tokens (HS256, 12 hours) from `POST /auth/session`. Every data route returns 401 without one | The wallet's own customer login. Thamun would trust the wallet's token or sit behind its gateway with mutual TLS |
| Authorisation | A token can be bound to one customer. Requests for another customer return 403 | Bind every token to the logged-in customer. The demo leaves this open so judges can switch customer |
| Admin access | Raw exports and the audit log need `X-Admin-Key`. With no key configured the routes are closed | Staff single sign-on and role-based access |
| Rate limiting | Per session and per address, in memory. 429 with `Retry-After`. Separate limits for new sessions, reports and feedback | A shared limiter at the gateway or in Redis, so limits hold across workers |
| Report abuse | One report per customer per number, five reports a day, confidence from distinct recent reporters, one count per outside session | Reporter reputation, manual review of high-impact numbers, an appeal path for a wrongly reported number |
| Input validation | Pydantic models for every request: types, lengths, patterns, fixed lists. Free text is length-limited and stripped | Same |
| Secrets | Environment variables only. `.env` is ignored by git. A random secret is generated if none is set, with a warning | A secrets manager and key rotation |
| Transport | HTTPS is provided by the hosts (Render, Vercel) | TLS inside the provider's network as well |
| CORS | `ALLOWED_ORIGINS` restricts browser origins | Set to the exact app origin. The API should not be public at all |
| Error handling | Unhandled errors return a generic message. Details go to the server log only | Same, plus central log collection |
| Response headers | `nosniff`, frame denial, no referrer, no caching of API responses | Same |
| Logging | Decision log without recipient numbers. Reports are logged without the number | Retention limits and access control on logs |
| Prompt injection | The decision path never reads free text. Purposes come from a fixed list. LLM output is checked number by number | Same |
| Dependencies | Version ranges in `api/requirements.txt` | Pinned hashes and scanning in CI |

## Known gaps, stated plainly

- The session token is issued to anyone who asks, because the demo has no login. It proves "same browser
  session", not "this person".
- The rate limiter, the demo wallet state and the live monitoring counters are in process memory. They
  reset when the server restarts and are not shared between workers.
- Tokens are kept in the browser's local storage, which is acceptable for a demo on synthetic data and
  not for a real wallet session.
- No penetration test and no independent security review have been done.
