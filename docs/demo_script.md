# Demo and video script

About four minutes. Run it on the live app with the Demo guide panel open. Press "Reset the demo" first.

## 1. The problem (30 seconds)

Say:

> Payment fraud cost Bangladesh 926 million taka in 2025. Most of it went through mobile wallets and only
> about one taka in ten was recovered. In most cases the real owner is talked into sending the money, so
> the OTP is entered by the right person and cannot help. Thamun, Bangla for "please pause", checks every
> payment against the customer's own history before the OTP, and coaches everyday spending with the same
> engine.

## 2. Rina's month (2 minutes)

Rina is a salaried worker. Her salary arrives on the 1st. Today is 8 October in the demo.

| Step | Click | Say |
|---|---|---|
| 1 | Run "Pay a bill that is due" (৳1,050), enter any OTP | A known biller and the usual amount. Thamun stays silent. Routine payments get no extra step |
| 2 | Run "Order food again" (৳450) | Her fifth order this week. One line tells her eating out is at ৳2,100, about 37% above her usual week. It does not block her |
| 3 | Run "Return money sent by mistake" (৳8,000) | A new number, so Thamun asks what the payment is for. This is the only time it asks |
| | Choose "Returning money sent to me by mistake" | Now the pause. Four times her usual amount, a number she has never paid, and no money ever arrived from that number, so the refund story is false. It would also leave her ৳1,200 short for electricity in two days |
| | Point at the right panel | Every reason is traceable: the model score, the SHAP contributions, and the purpose rule, which sits outside the model |
| | Press "Cancel payment" | She cancels. ৳8,000 stays in her wallet. She could also have paid anyway. Thamun never blocks |
| 4 | Run "Send a tiny amount to a reported number" (৳50) | Other customers have reported this number, so Thamun pauses whatever the amount and does not even ask the purpose. The first reason is the report count |
| | Press "Report this number as a scam", pick a reason, then "Cancel payment" | Her report is added. The next customer who tries to pay this number sees one more report |
| | Open Check, type a number, press Check | Before paying, anyone can look a number up: how many reports, what the callers asked for, and whether she has ever paid it. No reports does not mean safe, and the screen says so |
| 5 | Open Home | Bill readiness. Thamun found her bills from her history, forecasts her balance to each due date and tells her to cash in three days before one falls short |
| 6 | Open Review, then Goals, then Ask | Where September went, a plan to save ৳30,000 in six months, and a plain answer to "Why do I always run short before month-end?" |

## 3. The AI under the hood (1 minute)

Show the diagrams in `docs/diagrams/` or the inspector panel.

- A LightGBM model labels each payment and asks the customer only when it is unsure.
- A LightGBM classifier and an Isolation Forest score how unlike the customer a payment is, using features
  built from that customer's own history. SHAP values give the reasons.
- Purpose rules and the bill check are plain code, separate from the models.
- The LLM only words the message. It cannot change a number or a decision.
- Switch customer to Salma, an irregular earner, and run the prize-fee payment in Bangla to show the same
  rules work for a very different customer.

## 4. Evidence and impact (30 seconds)

Say:

> On a month the models never saw, Thamun paused 96% of injected scam payments with about 0.6 false
> pauses per customer per month, and completed 97% of payments without asking a single question. The data
> is synthetic and scam attempts are oversampled, so the next step is controlled validation on anonymised
> upay data. For upay this means fewer scam losses, more bills paid through the wallet and a reason for
> customers to make upay their main wallet.

## Questions judges may ask

| Question | Answer |
|---|---|
| What about a new customer with no history? | Features fall back to neutral values and the purpose rules still work. With real data, a segment-level baseline would be used until the customer has enough history |
| Why not put the rules in the LLM? | Decisions must be traceable and repeatable. The LLM never sees a decision it could change |
| Is it fair to low-income users? | Every customer is compared with their own history, and persona is not a model input. False pauses for irregular earners were the lowest of the four groups |
| What does it miss? | A scam sent through a known contact's hijacked account looks like a normal transfer. Device and location signals in a real wallet would help |
| Can someone report an honest number to harm them? | In this prototype one report is enough and each customer counts once per number. A pause never blocks, so a false report costs one extra screen. In production we would require several independent reporters, weigh them by their history and review heavily reported numbers |
| How would it plug into upay? | `POST /check` sits between the payment form and the OTP step. `ml/features.py` builds all features from a plain transaction stream |
