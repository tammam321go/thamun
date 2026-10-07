# Demo script for the final evaluation

About six minutes of demo, then questions. Run it on the live app with the Demo guide open on the left
and "Under the hood" on the right. Press "Reset the demo" first. Open the API address a minute before,
because the free server sleeps.

## 1. The problem (45 seconds)

Say:

> In Bangladesh the scammer no longer steals your password. They call you and talk you into sending the
> money yourself: "I sent you money by mistake, please return it", or "pay a fee to claim your prize".
> You type your own PIN and your own OTP, so to the wallet it is a normal payment. Bangladesh Bank figures
> reported in June put payment fraud at 926 million taka in 2025, about 88% of it through mobile wallets,
> and only about one taka in ten was recovered.
>
> Thamun, Bangla for "please pause", is a safety layer that sits before the OTP. It protects users from
> socially engineered payments, explains itself in Bangla or English, and leaves the decision with the
> customer. Pause. Understand. Decide.

## 2. The demo story (3 minutes)

Rina is a salaried worker. Today is 8 October in the demo. Each step is a button in the Demo guide.

| Step | Click | Say |
|---|---|---|
| 1 | "Pay a bill that is due" (৳1,050), any OTP | Known biller, usual amount. Thamun stays silent. In our test month 91.0% of payments went through like this, with no question and no message. That is our answer to "it will impact the customer experience" |
| 2 | "Order food again" (৳450) | One line above the OTP box: eating out is above her usual week. This is the money coach, not a fraud alert, and it never blocks |
| 3 | "Return money sent by mistake" (৳8,000), choose "Returning money sent to me by mistake" | A new number, so Thamun asks the purpose once. Now the red pause: three reasons, the rule first. No money ever arrived from this number, so the refund story is false |
| | Open "Why did Thamun pause this?" | The rest is one tap away, with the real values: share of her balance, the bill it would leave short, the risk score against the pause level |
| | Point at the right panel | The decision is split in three: what the models measured, which fixed rules fired, and how the message was worded. The language model never decides |
| | "Cancel payment" | Three exits on every pause: cancel, talk to someone first, or continue anyway. Thamun never blocks |
| 4 | "Send a tiny amount to a reported number" (৳50) | 37 different customers reported this number. Paused at once, even for fifty taka |
| 5 | "Send to a number with a single report" (৳200) | One report is only a caution. Nobody can make a number alarming for everyone by reporting it once. Confidence needs several different customers, and recent reports count more |
| 6 | "Send a large amount just before bills are due" (about ৳7,000). If it asks the purpose, choose "Paying or lending to a friend" | A different kind of pause, in teal: "Bill warning, not a scam alert". Nipa is a trusted contact. The risk model is calm. The bill forecast is not |
| 7 | Evidence, Impact, System tabs | Next section |

## 3. What changed since Phase 1 (2 minutes)

Go through the right panel tabs. Each one answers a judge comment.

| Tab | Say |
|---|---|
| Evidence | "All data is synthetic" is true and we cannot change that today. What we added: four models compared at the same false-pause budget, an ablation, and a stress test. We froze the models, generated new customers they had never seen, and changed two assumptions against ourselves. Recall went from 96.3% to 92.1%. We quote the lower number first |
| Evidence, further down | Two findings we did not hide. Random Forest is about as good as LightGBM, and we keep LightGBM for speed and exact SHAP values. The Isolation Forest added no scam payments in our tests, so it is marked for shadow testing |
| Impact | Three sources kept apart: simulation, this demo session, and real users, which says "not yet measured". User testing mode asks five questions after each warning and counts the answers here |
| System | Live requests, error rate, risk-check latency, drift check. The load test is real: 50 simultaneous users, 77.0 requests a second, no failures, 300 ms at the 95th percentile on one small worker, and we show where one worker saturates |
| System, bottom | Reports, the decision log and feedback are in SQL tables now. Session tokens, rate limits and an audit log are in. And nothing has to leave the country: the models are small files on ordinary CPUs, and a public LLM is refused by default |

## 4. Close (20 seconds)

> Thamun is sold to the wallet, free for the customer. What we have is a working engine, honest synthetic
> evidence and a plan for validating on real data in four stages. What we do not have yet is real
> customers, and we say so on screen.

## Numbers worth remembering

| Number | Meaning |
|---|---|
| 96.3% of 54 | Scam payments paused in the held-out month |
| 92.1% of 190 | The same models on new customers they never saw |
| 0.58 and 0.66 | False pauses per customer per month, original and new customers |
| 91.0% | Payments with no interruption at all |
| 2.7% | Payments where the purpose is asked |
| 3 and 10 | Report score for "likely" and "confirmed". One recent report counts 1, older ones count less |
| 50 users, 77.0 requests a second, 300 ms | Load test on one worker |
| 44 | Automated tests |

Always add "on synthetic data" when quoting a model number.

## Questions judges may ask

| Question | Answer |
|---|---|
| Your data is still synthetic. What is different now? | We stopped quoting one number from one test. We froze the models and tested them on new populations and with two assumptions changed against us. Recall dropped from 96.3% to 92.1% and we report that. The next step needs a wallet partner: offline replay on anonymised history inside their environment, then shadow mode |
| Why LightGBM and not Random Forest? | On accuracy they are within one payment of each other in our test. LightGBM scores a payment in a fraction of a millisecond, is a 300 KB file and gives exact SHAP values. A check sits before OTP, so speed matters |
| Then why keep the Isolation Forest? | Our own ablation says it added nothing on synthetic data. We left it on today so the decision behaviour did not change on the final day without a full re-test. In shadow mode on real data it either catches something LightGBM missed or it is removed |
| What stops someone reporting an honest number? | One report per customer per number, five reports a day, and one report is only a caution. A pause needs several different customers, with recent reports counting more. A pause never blocks. Production would add reporter reputation, manual review and an appeal path |
| Where does customer data go? | Nowhere. Models and rules run inside the API process on ordinary CPUs. The only component that could call out is the optional language model, and by default it is refused unless its address is internal |
| What is still in memory? | The sandbox copy of the four demo customers, one per browser session, so judges do not affect each other. Also the rate limiter and live counters. Reports, the decision log and feedback are in the database. In a wallet, history comes from the ledger and a feature store |
| Did you test with real users? | The tool is built and counts answers in the Impact tab. Whatever number is shown there is what was actually collected. We do not claim a result we did not measure |
| What happens if Thamun is down? | The payment service continues to OTP as it does today. Thamun must never be able to stop payments by failing |
| Can it handle a real wallet's volume? | One worker handled 77.0 requests a second on a two-core machine and then queued. Workers become stateless once history comes from a feature store, so capacity grows by adding workers. That scaling is the design and has not been measured |
| Does the LLM decide anything? | No. Decisions are made by code from model scores and rules. The LLM may only reword a finished message, and the reworded text is thrown away unless every number matches. The live demo runs with no LLM at all |
| What does it miss? | A scam sent through a known contact's hijacked account. It looks like a normal transfer to a friend. Device and location signals in a real wallet would help |
| What about a new customer with no history? | Features fall back to neutral values and the purpose rules and report list still work. With real data a segment baseline would be used until the customer has history |
| How does the wallet make money from this? | It does not charge the customer. The provider pays because an authorised scam costs a complaint, an unrecovered loss and often the customer. We defined the measures and the control-group design. None is measured yet |
| Did you use AI tools? | Yes, an AI coding assistant, as the rules allow. We can explain every file |

## Who explains what

| Member | Area |
|---|---|
| Tammam Ibn Aman | Data generator, features, models, experiments, evaluation |
| Sachin Sarker | API, database, security, monitoring, load test |
| Deep Mitra | Web app, pause page, user testing mode, the four panel tabs |

Every member should be able to give the 45-second problem statement and walk the demo story.
