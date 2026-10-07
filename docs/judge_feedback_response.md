# Phase 1 judge feedback: what we changed and where to check it

Every row points at code, a document or a screen. Where something is not done or not measured, the row
says so.

## Summary table

| Judge feedback | What we changed | Evidence |
|---|---|---|
| **Problem relevance.** "The problem statement needs to be addressed clearly." | The problem is now stated as one thing: authorised push payment scams on Bangladeshi mobile wallets, where the customer is talked into paying and OTP cannot help. A sourced national figure is given. Coaching is presented as a second, separate job | README section 1. The "The problem" block at the top of the Demo guide in the app |
| **AI/ML depth.** "All the data is synthetic, so performance on real customer data is still unknown." | We cannot fix this without real data and we do not claim to. We added what can be done honestly: four models compared at an equal false-pause budget, calibration, feature-group ablation, decision-layer ablation, a test on scam types hidden from training, and a stress test on new populations with two assumptions changed against us | `ml/experiments.py`, `docs/model_comparison.md`, Evidence tab. Result on new populations: 92.1% of 190 scam payments paused, against 96.3% on the original held-out month |
| **Business impact.** "BI need to address more clearly." "Real business impact has not yet been tested with actual users or real transaction data." "Metrics are bounded by synthetic simulator assumptions." | A B2B2C business model with who pays and why. Impact measures defined against a control group. An Impact tab that keeps three sources apart: simulation, live demo use, and real users marked "not yet measured". A user-testing mode that collects anonymous answers. A validation roadmap with exit tests | `docs/business_model.md`, `docs/validation_roadmap.md`, Impact tab, `POST /feedback`, `GET /analytics` |
| **Prototype quality.** "Some parts still use demo or session-based data, so it is not fully production-ready yet." | Scam reports, the decision log and user-testing answers moved to SQL tables. The remaining in-memory part is the sandbox copy of the four demo customers, which exists so that judges do not affect each other. It is labelled as demo-only and its production replacement is described | `api/db.py`, `api/reports.py`, `docs/architecture.md` ("What is real and what is demo"), test `test_database_keeps_reports_after_a_restart` |
| **Innovation.** "Innovation is good but it will impact the customer experience." | Measured the friction: 91.0% of payments are never interrupted and the purpose is asked on 2.7%. One report no longer pauses a payment. The pause page shows three reasons and hides the rest behind one tap. Bill warnings look different from scam alerts. Every pause has the same three exits | README section 8, `docs/evaluation.md` ("Customer experience"), the redesigned pause page, demo story steps 5 and 6 |
| **Scalability.** "Does not yet show large-scale testing, real transaction load handling, or production monitoring." | A Locust load test that was actually run: 50 simultaneous users, 77.0 requests a second, no failures, risk check 300 ms at the 95th percentile on one worker, plus the stages where one worker saturates. A live monitoring endpoint and System tab. A drift check and retraining plan. A production architecture | `loadtest/`, `api/evidence/load_test.json`, `api/monitor.py`, `GET /monitoring`, System tab, `docs/architecture.md` |
| **Scalability.** "Relying on in-memory report state rather than persistent database tables." | Reports are rows in a `scam_reports` table with a unique constraint per reporter and number. SQLite locally, PostgreSQL when `DATABASE_URL` is set. Verified against a PostgreSQL 16 server | `api/db.py`, `api/reports.py`, `render.yaml`, `GET /health` shows the backend in use |
| **Responsible AI.** "Since wallet data cannot be transferred across borders, an internally hosted AI solution is recommended." | The decision path never called an external service and still does not. The one optional external component, the language model, is now refused by default unless its address is internal (`LLM_DATA_RESIDENCY=internal_only`) | `api/explain.py` (`llm_status`), `api/security.py` (`internal_host`), `docs/privacy_security.md`, test `test_external_llm_is_off_unless_explicitly_allowed`, Decision tab part 3 |
| **Responsible AI.** "Better authentication and stronger production security would still be needed." | Signed session tokens, optional binding of a token to one customer, per-session and per-address rate limits, an admin key for exports, an audit log that never stores the recipient, security headers, generic error messages, stricter checks on LLM output, abuse limits on reports. What production still needs is listed next to each control | `api/security.py`, `tests/test_platform.py`, `docs/privacy_security.md` |

## What is still not done

| Item | Status |
|---|---|
| Any test on real customers or real transactions | Not done. Needs a wallet partner |
| User-testing results | The tool is built. No result is claimed in this repository. Counts appear in the Impact tab as people use it |
| Multi-worker or cluster load test, PostgreSQL under load | Not measured |
| Real customer login, shared rate limiter, secrets manager, penetration test | Not done |
| Value of the reported-number list | Not measured. The simulator uses each scam number once |
| Tuning of report confidence levels | Starting values only |

## Honest findings from the new experiments

- On newly generated customers the models never saw, recall is 92.1% with 0.66 false pauses
  per customer per month. That is lower than the 96.3% and 0.58 on the original held-out month,
  and it is the figure we now quote first.
- Random Forest performs about as well as LightGBM. LightGBM is kept for speed, size and exact SHAP
  values, not because it is clearly more accurate.
- The Isolation Forest added 0 scam payments and 23 false pauses in the test month,
  and nothing on scam types hidden from training. It is a candidate for removal after shadow testing.
- Impersonation through a known contact's account is still mostly missed.

## New and changed files

| Area | Files |
|---|---|
| Database | `api/db.py` (new), `api/reports.py` (rewritten), `api/store.py` |
| Security | `api/security.py` (new), `api/main.py`, `.env.example`, `render.yaml` |
| Monitoring | `api/monitor.py` (new), `GET /monitoring`, `web/src/components/SystemPanel.jsx` |
| ML evidence | `ml/experiments.py` (new), `ml/evaluate.py`, `data/generate.py`, `data/personas.py`, `api/evidence/` |
| Load test | `loadtest/locustfile.py`, `loadtest/run.py` (new) |
| Customer experience | `web/src/screens/Home.jsx`, `web/src/screens/Pay.jsx`, `web/src/components/FeedbackForm.jsx` (new) |
| Explainability | `web/src/components/Inspector.jsx`, `SidePanel.jsx`, `Evidence.jsx`, `Impact.jsx` (new) |
| Tests | `tests/test_platform.py`, `tests/conftest.py` (new), `tests/test_engine.py` |
| Documents | this file, `docs/architecture.md`, `docs/privacy_security.md`, `docs/business_model.md`, `docs/validation_roadmap.md`, `docs/model_comparison.md` |
