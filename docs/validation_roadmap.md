# Validation roadmap

Phase 1 feedback: "all the data is synthetic, so performance on real customer data is still unknown" and
"metrics are bounded by synthetic simulator assumptions". Both are correct. This page states what has been
measured, what has not, and the order in which the gaps would be closed.

## Where the evidence stands today

| Claim | Status | Where to check |
|---|---|---|
| Scam payments paused in a held-out month of the simulator | Measured (synthetic) | `docs/evaluation.md` |
| Same models on newly generated customers they never saw | Measured (synthetic) | `docs/model_comparison.md`, section 7 |
| Same models when two simulator assumptions are changed against us | Measured (synthetic) | `docs/model_comparison.md`, section 7 |
| A scam type that was removed from training | Measured (synthetic) | `docs/model_comparison.md`, section 5 |
| Share of payments that are never interrupted | Measured (synthetic) | `docs/evaluation.md`, customer experience |
| API speed under load | Measured on one machine | `api/evidence/load_test.json` |
| People understand the pause screen | User-testing mode is built. Responses are counted live in the Impact tab. No result is claimed in this repository |
| Performance on real wallet transactions | Not yet measured |
| Fraud losses prevented, bills paid on time, money saved by real users | Not yet measured |
| Value of the reported-number list | Not yet measured. The simulator uses each scam number once |

## What the stress test does and does not prove

`python -m ml.experiments` freezes the trained models and thresholds, then generates new populations with
different random seeds and with two assumptions changed:

- `MODEST_SCAM_SHARE` raised from 0.3 to 0.7: most scammers ask for an amount close to the customer's normal.
- `PURPOSE_HONESTY_SCALE` lowered from 1.0 to 0.3: most victims are coached to hide the real purpose.

It shows how far the headline number moves when our own assumptions are wrong in a known direction. It
cannot show what happens with scam patterns nobody on the team imagined. Only real data can.

## Stages

| Stage | What happens | Data | Exit test, fixed before the stage starts |
|---|---|---|---|
| 0. Simulation (done) | Train, test, ablate and stress on generated data | Synthetic | Scripts are reproducible from a fixed seed |
| 1. Offline replay | Rebuild features from anonymised history inside the wallet provider's own environment. Confirmed fraud complaints are the labels | Real, never leaves the provider | Recall on confirmed scam payments at 0.5 false pauses per customer per month, reported by scam type and customer segment |
| 2. Shadow mode | The engine scores live payments. Nothing is shown to customers. Decisions are logged and compared with fraud confirmed later | Real, live | False pause rate on real traffic. Latency at the 95th percentile. Whether the Isolation Forest catches anything LightGBM misses |
| 3. Pilot | A random group of customers sees pauses and nudges. A control group does not | Real, live, consented | Scam loss per 1,000 customers against control. Share of pauses cancelled. Complaints and support contacts per 1,000 pauses. Payment completion rate |
| 4. Rollout | Wider release with drift monitoring and a retraining schedule | Real, live | Agreed with the provider's risk team |

## Decisions that are waiting for real data

- **Isolation Forest.** On synthetic data it added no scam payments and about 0.1 false pauses per customer
  per month. It stays switched on for now so that the decision behaviour is unchanged on the final day. In
  stage 2 it runs in shadow. If it still catches nothing that LightGBM missed, it is removed.
- **Report confidence levels.** A score of 3 means "likely" and 10 means "confirmed". These are starting
  values, not tuned values. Stage 1 would set them from how often real scam numbers are reused.
- **Pause budget.** 0.4 plus 0.08 false pauses per customer per month was chosen by the team. The provider
  would choose this number from its own complaint and loss data.

## User testing protocol

User-testing mode is in the app (Demo guide, "User testing mode").

1. The tester opens the live app, switches user testing on and hands the phone to a participant.
2. The participant runs the six demo story payments. No real account, PIN or OTP is involved.
3. After each warning the phone asks five questions in the participant's language: was the message
   understood, was the reason clear, was it too intrusive, was it clear the decision was still theirs,
   and which language is easier.
4. Answers are stored with the scenario and the decision only. No name, phone number or session id is
   kept with an answer.
5. Totals are shown in the Impact tab and can be exported as JSON. Raw rows need the admin key.

Target for a first round: 20 to 30 participants, at least half Bangla-first and at least a third who
describe themselves as not confident with apps. What would change the design: more than one in four
participants answering "no" to "was it clear the decision was still yours", or more than one in three
answering "yes" to "did it interrupt you too much".

Numbers from user testing are reported only as counted by the app. None are written by hand into this
repository.
