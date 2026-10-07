# Evaluation on the held-out month

Test month: 2026-09 (never used for training or threshold selection). Customers: 200.
All data is synthetic. Scam attempts are oversampled, so precision would be lower at real-world rates.

## Guard

| Metric | Value |
|---|---|
| Scam payments in test month | 54 in 39 incidents |
| Scam payments paused | 96.3% (95% interval 87.5% to 99.0%) |
| Incidents paused at the first payment | 94.9% |
| Scam money paused | 88.9% |
| Caught by the behaviour model alone | 96.3% |
| Caught by purpose rules alone | 55.6% |
| False pauses per customer per month | 0.575 |
| Affordability pauses per customer per month | 0.295 |
| Unusual but legitimate payments paused | 30.9% |

### By scam type

| Scam type | Payments in test month | Payments paused |
|---|---|---|
| account_takeover | 5 | 100.0% |
| fake_agent_call | 4 | 100.0% |
| impersonation | 4 | 50.0% |
| prize_fee | 18 | 100.0% |
| refund_scam | 23 | 100.0% |

### Fairness by persona

| Persona | Scam payments paused | False pauses per customer-month | All pauses per customer-month |
|---|---|---|---|
| irregular | 100.0% | 0.25 | 0.725 |
| salaried | 95.2% | 0.6625 | 1.3875 |
| shop_owner | 85.7% | 0.6667 | 1.4333 |
| student | 100.0% | 0.64 | 0.86 |

## Customer experience (alert fatigue)

| Metric | Value |
|---|---|
| Outgoing payments in the test month | 9178 |
| Went straight to OTP with no question and no message | 91.0% |
| Silent decisions | 92.2% |
| Nudges (one line, payment continues) | 5.3% |
| Pauses (full screen, customer still decides) | 2.5% |
| Genuine payments that were paused | 1.9% |
| Asked "what is this payment for?" | 2.7% |

## Labels

| Metric | Value |
|---|---|
| Category accuracy | 96.2% |
| Auto-labelled with confidence | 95.6% |
| Accuracy of auto-labels | 97.1% |
| Payments completed without asking the purpose | 97.3% |

## Bills

| Metric | Value |
|---|---|
| Recurring bills found (recall) | 98.9% |
| Detected bills that are real (precision) | 99.5% |
| Due date error | 0.35 days |
| Amount error | 2.8% |
| Shortfalls flagged 3 days ahead (recall) | 74.6% |
| Shortfall flags that were right (precision) | 56.5% |

## Nudges

| Metric | Value |
|---|---|
| Spending nudges per customer per month | 1.45 |
| Bill-due nudges per customer per month | 1.0 |
| Nudges in weeks truly above the customer's usual | 89.0% |
| Clear overspending weeks (50% above usual) that got a nudge | 50.9% of 399 |
| Most spending nudges for one customer in one week | 2 |

## Limits of this evaluation

- The models are trained and tested on data from the same simulator, so these numbers are optimistic. Real scams will differ from the injected ones.
- The test month holds few scam payments, which is why the interval above is wide.
- A scam where a known contact's account is used (impersonation) looks like a normal transfer to a friend, and most of those are missed.
- Scam attempts are injected far more often than they happen in reality. False pauses per customer per month do not depend on that rate, so that figure is the one to compare.
