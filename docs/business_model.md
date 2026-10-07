# Business model

Phase 1 feedback: "BI need to address more clearly" and "real business impact has not yet been tested
with actual users or real transaction data". This page says who pays, why, and how impact would be
measured. It contains no revenue or savings figures, because none have been measured.

## Who it is for (B2B2C)

| Party | Role | What they get |
|---|---|---|
| Wallet provider (for example upay) | Buys and runs Thamun | Fewer scam losses and complaints, a visible safety feature, more bills paid through the wallet |
| Wallet customer | Uses it for free inside the app they already have | A warning before the money leaves, a reminder before a bill fails, a savings plan |
| Regulator and the wider ecosystem | Not a customer | Reported numbers and anonymous pause statistics that a provider can share with its risk team |

The customer never pays, sees no advertising and is never offered a loan. If the product earned money
from the customer's spending, its advice could not be trusted.

## Why a provider would pay

Bangladesh Bank data reported by The Financial Express (16 June 2026) puts payment fraud at Tk 926.01
million in 2025, with mobile financial services at about 88% of the value and 10.7% recovered. Most of
that money is sent by the account owner, who has been talked into it, so stronger logins do not stop it.

For a provider the cost of an authorised scam is more than the amount lost:

- the complaint has to be handled by a person,
- the money is almost never recovered, so the customer blames the wallet,
- a customer who has been scammed often keeps less money in the wallet or leaves.

Thamun acts at the only moment where the loss can still be avoided: after the customer has decided to
pay and before the OTP.

## How it would be sold

| Option | How it works | Fits when |
|---|---|---|
| Licence, run on the provider's own servers | Yearly fee by number of active customers. Models, data and logs stay in the provider's data centre | Data must stay inside Bangladesh, which is the expected case |
| Managed service inside the country | Same software, hosted for the provider in a local data centre | A smaller provider without its own ML team |
| Outcome-linked fee | A lower base fee plus a share of the measured reduction in scam loss against a control group | The provider wants the supplier to carry part of the risk |

## How impact would be measured

Every figure below is a definition, not a result.

| Goal | Measure | Compared with |
|---|---|---|
| Safety | Scam loss per 1,000 active customers per month | A random control group without pauses |
| Safety | Share of pauses that end in a cancelled payment | Share later confirmed as fraud |
| Customer experience | False pauses per customer per month, complaints per 1,000 pauses, payment completion rate | Control group |
| Financial health | Bills paid on or before the due date, customers who cash in after a reminder, savings goals reached | The same customers before the feature, and control |
| Business | Balance kept in the wallet, 90-day retention, support contacts about fraud | Control group |

Break-even for the provider is a formula it can fill with its own numbers:

```
monthly value = scam loss avoided
              + complaint handling cost avoided
              + margin on balances and payments kept
              - cost of handling false pauses
              - licence and running cost
```

## What the prototype already shows

- The engine answers a risk check in milliseconds on an ordinary CPU, so running cost per customer is low.
  See the load test in `api/evidence/load_test.json`.
- In simulation about nine in ten payments are never interrupted, which is what keeps complaint cost low.
- The Impact tab in the app separates three sources: simulation, live use of the demo, and real users
  (not yet measured).
