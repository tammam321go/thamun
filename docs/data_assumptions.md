# Synthetic data assumptions

Every number Thamun learns from is produced by `data/generate.py` from the settings in `data/personas.py`.
No real customer, merchant or transaction data is used anywhere. This file lists every assumption the
generator makes, so a reviewer can judge how far the results can be trusted.

## What is generated

| File | Contents |
|---|---|
| `data/out/transactions.csv` | About 113,000 transactions for 200 customers, 1 April to 30 September 2026 |
| `data/out/customers.csv` | Customer id, persona, monthly income, main income day |
| `data/out/bill_events.csv` | Every bill and regular transfer: due date, paid time, whether the balance was short on the due date, days late |
| `data/out/recurring_truth.csv` | The true list of each customer's recurring bills and transfers |
| `data/out/spend_truth.csv` | Each customer's true long-run weekly spending per category |
| `data/out/splurges.csv` | Weeks in which a customer was made to overspend in one category |
| `api/demo_data/` | Four demo customers with history up to noon on 8 October 2026 (committed to the repo) |

The random seed is fixed at 42. Each customer has their own random stream, so the same command always
produces the same training data on the same library versions.

## Time split

| Months | Use |
|---|---|
| April to July | Fit the models |
| August | Choose the label confidence threshold and the pause thresholds |
| April to August | Refit the final models with the chosen settings |
| September | Test month. Never used for fitting or for choosing a threshold |

## Personas

| Persona | Customers | Monthly wallet income | How money arrives |
|---|---|---|---|
| Salaried worker | 80 | ৳26,000 to ৳62,000 | One salary payment on a fixed day between the 1st and 5th |
| Student | 50 | ৳6,000 to ৳14,000 | Monthly allowance from a parent, sometimes a mid-month top-up, 40% have tutoring income |
| Shop owner | 30 | ৳60,000 to ৳160,000 | Many small payments from customers on open days, usually closed on Fridays |
| Irregular earner | 40 | ৳9,000 to ৳20,000 | A payment on about 55% of days, with amounts that vary widely |

Persona is never given to a model. It is used only to generate data and to check fairness afterwards.

## The wallet

- Every customer starts with a small balance, 5% to 25% of monthly income.
- If a payment is larger than the balance, the customer either cashes in first (rounded up to ৳500) or
  skips the payment and pays in cash. The chance of cashing in is 80% for salaried workers, 45% for
  students, 85% for shop owners and 30% for irregular earners.
- When the balance grows past a personal holding limit, the customer cashes out the surplus on about one
  day in three.
- Fees and charges are not modelled.
- Timestamps follow hour-of-day patterns that differ by category: meals at lunch and dinner, transport at
  commuting hours, students later at night.

## Bills and regular transfers

- Salaried workers: electricity 85%, internet 80%, gas 60%, water 50%, a savings scheme 30%. Rent 55%,
  monthly family support 60%.
- Students: internet 45%, shared rent 50%.
- Shop owners: electricity 90%, internet 50%, water 30%, shop rent 80%.
- Irregular earners: internet 15%, no other regular bills.
- Each bill has a fixed due day. Customers pay between two days early and one day late.
- Electricity and water amounts vary by about 6% a month. Electricity is higher from May to August.
- Gas is a flat ৳1,080. Internet and savings are fixed amounts.
- If the balance is short on the due date, the customer either cashes in and pays, or pays 1 to 6 days
  late. The chance of paying late is 5% (salaried), 10% (student), 8% (shop owner), 30% (irregular).

## Everyday spending

- Each persona has a list of spending lines (category, payment type, weekly rate, typical amount, spread).
  Each customer gets their own rates and amounts, scaled to their income.
- Counts follow a Poisson distribution and amounts a log-normal distribution.
- Friday and Saturday raise eating out and shopping by 30%. Friday lowers transport by 40%.
- For salaried workers and students, eating out, shopping and transport rise by 25% in the week after
  income arrives.
- Eid window, 17 to 27 May 2026: shopping doubles, groceries rise by 50%, transport by 40%, eating out by
  20%, and 60% of customers who support family send an extra gift.
- Overspending weeks: in each week, each of eating out, shopping and transport has a 7% chance of running
  at 1.8 to 2.6 times the normal rate.
- 3% of payments carry the label "other" instead of their true category, to mimic messy labels.
- New counterparties: 10% of payments for salaried workers, 15% for students, 12% for shop owners and
  irregular earners go to a merchant, agent or person never paid before. Purchases from online sellers by
  send money go to a new number 75% of the time.

## Unusual but legitimate payments

These exist so that the risk model cannot simply learn that "large and new means scam".
Rates are 0.2 to 0.3 events per customer per month.

| Event | What happens |
|---|---|
| Big purchase | ৳4,000 to ৳28,000 sent to a seller never paid before |
| Lending to a friend | ৳3,000 to ৳12,000 to a known friend |
| Emergency | ৳3,000 to ৳15,000 to family or a new number, 30% at night |
| True refund | A stranger really sends money by mistake and the customer sends the same amount back |
| Big cash-out | ৳5,000 to ৳20,000 at an agent never used before |
| Tuition (students) | ৳8,000 to ৳25,000 to an education merchant |

## Scam scenarios

Scam attempts are injected at 0.26 to 0.32 per customer per month. This is far above real life and is
done on purpose so that the test month contains enough cases to measure. Every scam payment is recorded
as completed, as it would be in a wallet with no guard.

| Scenario | What happens | What the victim says if asked the purpose |
|---|---|---|
| Refund scam | Send ৳2,000 to ৳15,000 (৳1,000 to ৳6,000 for students and irregular earners) to a new number. In 20% of cases the scammer first sends ৳20 to ৳300 for real. 25% get a second request within 90 minutes | 75% say "returning money sent by mistake" |
| Prize fee | One to three payments to a new number, each 1.5 to 2.5 times the last, 20 to 120 minutes apart | 65% say "fee to claim a prize" |
| Fake agent call | One transfer of 50% to 95% of the balance to a new number | 60% say "someone on the phone asked me" |
| Account takeover | Mostly at night. A cash-out of 60% to 90% of the balance at a new agent, then one or two transfers of most of the rest, minutes apart | The attacker gives an innocent answer |
| Impersonation | A known friend or family contact's account asks for 1.5 to 6 times the usual transfer | The victim believes it and says "friend" or "family" |

30% of refund, prize and takeover scams are "modest": the amount is close to what the customer normally
sends, so only the stated purpose can reveal them. Victims who do not give the honest answer pick a
random innocent purpose.

## Identifiers

- Phone numbers start with 010, a prefix that no Bangladeshi operator uses as far as we know, so a
  generated number should not match a real subscriber.
- Merchant, biller and agent names are invented. Person names are common first names with a role, used
  only for the four demo customers.

## Reported scam numbers

- `api/demo_data/reported_numbers.json` is a hand-written dummy list of five numbers with a report count
  (37, 12, 6, 3 and 1), the most common complaint and the date of the last report. They use the 010
  prefix like every other generated number and do not appear in any customer's history.
- The reported-number rule plays no part in training or in the measured results. The simulated
  transactions contain no report data.
- Reports made in the app are stored in memory per browser session and count each demo customer once
  per number. They disappear on "Reset the demo" or when the server restarts.

## Demo customers

| Customer | Persona | Notes |
|---|---|---|
| Rina Akter | Salaried | Fully scripted profile: salary ৳45,000 on the 1st, rent ৳15,000 on the 3rd, family support ৳8,000 on the 5th, internet ৳1,050 on the 8th, electricity about ৳2,500 on the 10th, savings ৳3,000 on the 12th, gas ৳1,080 on the 15th, water on the 20th. She eats out four times a week. Her four orders in the demo week and her starting balance of ৳10,800 are set by hand so the demo story is repeatable |
| Tanvir Hasan | Student | Generated like any student, with no scams in his history |
| Karim Uddin | Shop owner | Generated like any shop owner, with no scams in his history |
| Salma Begum | Irregular earner | Generated like any irregular earner, with no scams in her history |

The demo clock is fixed at 8 October 2026, 13:10, and moves forward 37 minutes after each payment.

## Known gaps between this data and reality

- Real scams change faster and are more varied than five scripted scenarios.
- Device, location and network signals are not simulated, although a real wallet has them.
- Customers in the simulation answer the purpose question in fixed proportions. Real answers under
  pressure from a scammer are unknown.
- Income and spending are independent of the wider economy, prices and seasons other than Eid.
- The same simulator produces the training and the test data, so the reported scores are an upper bound.
