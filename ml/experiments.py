import argparse
import io
import json
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from data import generate as generator
from data import personas as P
from ml import evaluate, risk
from ml.features import RISK_CATEGORICAL, RISK_FEATURES, build_table, load_transactions
from ml.train import BEHAVIOUR_BUDGET, ISOLATION_BUDGET, MATERIAL_MIN, pick_threshold, split

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "out"
DOCS = ROOT / "docs"
EVIDENCE = ROOT / "api" / "evidence"
TOTAL_BUDGET = BEHAVIOUR_BUDGET + ISOLATION_BUDGET
SCORE_EDGES = [0.001, 0.005, 0.02, 0.05, 0.2, 0.5]
CALIBRATION_EDGES = [0.0, 0.01, 0.05, 0.2, 0.5, 1.0000001]

GROUPS = {
    "payment_fields": ["log_amount", "type_idx", "cp_type_idx"],
    "amount_vs_own_history": ["amt_ratio_type", "amt_pct", "amt_pct_type", "amt_ratio_max", "n_out"],
    "recipient_history": ["is_new_cp", "cp_count", "cp_age_days", "in_cp_ratio"],
    "balance_impact": ["balance_share"],
    "timing": ["hour", "hour_share", "is_night"],
    "velocity": ["n_1h", "n_24h", "sum_1h_ratio", "sum_24h_ratio", "new_cp_24h", "mins_since_last", "in_1h_ratio"],
}
GROUP_NAMES = {
    "payment_fields": "Raw payment fields (amount, type, recipient type)",
    "amount_vs_own_history": "Amount compared with the customer's own history",
    "recipient_history": "Recipient history",
    "balance_impact": "Share of balance",
    "timing": "Time of day",
    "velocity": "Speed and sequence in the last hour and day",
}
STRESS = [
    {"id": "new_customers_a", "name": "New customers (seed 7)", "seed": 7, "modest": 0.3, "honesty": 1.0},
    {"id": "new_customers_b", "name": "New customers (seed 101)", "seed": 101, "modest": 0.3, "honesty": 1.0},
    {"id": "new_customers_c", "name": "New customers (seed 2026)", "seed": 2026, "modest": 0.3, "honesty": 1.0},
    {"id": "ordinary_amounts", "name": "Scammers ask for ordinary amounts (70% of scams, was 30%)", "seed": 7, "modest": 0.7, "honesty": 1.0},
    {"id": "coached_victims", "name": "Victims coached to hide the purpose (honesty x 0.3)", "seed": 7, "modest": 0.3, "honesty": 0.3},
    {"id": "both_shifts", "name": "Both shifts together", "seed": 7, "modest": 0.7, "honesty": 0.3},
]


def signed_log(values: np.ndarray) -> np.ndarray:
    return np.sign(values) * np.log1p(np.abs(values))


def logistic() -> Any:
    numeric = [f for f in RISK_FEATURES if f not in RISK_CATEGORICAL]
    columns = ColumnTransformer([
        ("numeric", make_pipeline(FunctionTransformer(signed_log), StandardScaler()), numeric),
        ("categorical", OneHotEncoder(handle_unknown="ignore"), RISK_CATEGORICAL),
    ])
    return make_pipeline(columns, LogisticRegression(C=1.0, class_weight="balanced", max_iter=3000))


def forest() -> Any:
    return RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced_subsample",
                                  random_state=42, n_jobs=2)


def material_legit(table: pd.DataFrame) -> np.ndarray:
    return (table["is_scam"].to_numpy() == 0) & (table["amount"].to_numpy() >= MATERIAL_MIN)


def at_threshold(table: pd.DataFrame, flagged: np.ndarray, customers: int) -> dict[str, Any]:
    scam = table["is_scam"].to_numpy() == 1
    flagged = flagged & (table["amount"].to_numpy() >= MATERIAL_MIN)
    caught = int((flagged & scam).sum())
    false = int((flagged & ~scam).sum())
    precision = caught / (caught + false) if caught + false else None
    recall = caught / int(scam.sum()) if scam.sum() else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    return {
        "scams_caught": caught, "scam_payments": int(scam.sum()),
        "recall": evaluate.rate(caught, scam.sum()), "recall_interval": evaluate.wilson(caught, int(scam.sum())),
        "precision": round(precision, 4) if precision is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "false_pauses": false, "false_pauses_per_customer_month": evaluate.rate(false, customers),
    }


def ranking(table: pd.DataFrame, scores: np.ndarray) -> dict[str, Any]:
    target = table["is_scam"].to_numpy()
    customers = int(table["customer_id"].nunique())
    threshold = pick_threshold(scores[material_legit(table)], int(TOTAL_BUDGET * customers))
    caught = int(((scores >= threshold) & (target == 1) & (table["amount"].to_numpy() >= MATERIAL_MIN)).sum())
    return {"pr_auc": round(float(average_precision_score(target, scores)), 4),
            "roc_auc": round(float(roc_auc_score(target, scores)), 4),
            "scams_at_equal_budget": caught, "recall_at_equal_budget": evaluate.rate(caught, int(target.sum()))}


def speed(predict: Callable[[pd.DataFrame], Any], test: pd.DataFrame, rows: int = 200) -> float:
    sample = test[RISK_FEATURES].head(rows)
    started = time.perf_counter()
    for i in range(len(sample)):
        predict(sample.iloc[[i]])
    return round((time.perf_counter() - started) * 1000 / len(sample), 2)


def pickled_kb(model: Any) -> int:
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    return int(round(buffer.tell() / 1024))


def supervised(make: Callable[[], Any], fit: pd.DataFrame, valid: pd.DataFrame, train: pd.DataFrame,
               test: pd.DataFrame, allowed: int) -> tuple[Any, np.ndarray, float]:
    first = make().fit(fit[RISK_FEATURES], fit["is_scam"].astype(int))
    valid_scores = first.predict_proba(valid[RISK_FEATURES])[:, 1]
    threshold = pick_threshold(valid_scores[material_legit(valid)], allowed)
    final = make().fit(train[RISK_FEATURES], train["is_scam"].astype(int))
    return final, final.predict_proba(test[RISK_FEATURES])[:, 1], threshold


def boosted(features: list[str], fit: pd.DataFrame, valid: pd.DataFrame, train: pd.DataFrame,
            test: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, Any]:
    categorical = [f for f in RISK_CATEGORICAL if f in features]

    def dataset(frame: pd.DataFrame, reference: Optional[lgb.Dataset] = None) -> lgb.Dataset:
        return lgb.Dataset(frame[features], label=frame["is_scam"].astype(int), categorical_feature=categorical,
                           reference=reference, free_raw_data=False)

    base = dataset(fit)
    first = lgb.train(risk.PARAMS, base, num_boost_round=500, valid_sets=[dataset(valid, base)],
                      callbacks=[lgb.early_stopping(40, verbose=False)])
    final = lgb.train(risk.PARAMS, dataset(train), num_boost_round=first.best_iteration)
    return first.predict(valid[features]), final.predict(test[features]), final


def compare_models(fit: pd.DataFrame, valid: pd.DataFrame, train: pd.DataFrame, test: pd.DataFrame) -> dict[str, Any]:
    customers = int(valid["customer_id"].nunique())
    test_customers = int(test["customer_id"].nunique())
    allowed = int(TOTAL_BUDGET * customers)
    rows = []

    for name, make in (("Logistic regression", logistic), ("Random forest", forest)):
        started = time.time()
        model, scores, threshold = supervised(make, fit, valid, train, test, allowed)
        seconds = round(time.time() - started, 1)
        rows.append(dict(model=name, kind="supervised baseline", **ranking(test, scores),
                         brier=round(float(brier_score_loss(test["is_scam"], scores)), 5),
                         **at_threshold(test, scores >= threshold, test_customers), train_seconds=seconds,
                         ms_per_payment=speed(model.predict_proba, test), size_kb=pickled_kb(model)))

    started = time.time()
    valid_prob, test_prob, booster = boosted(RISK_FEATURES, fit, valid, train, test)
    alone = pick_threshold(valid_prob[material_legit(valid)], allowed)
    rows.append(dict(model="LightGBM", kind="supervised, used in Thamun", **ranking(test, test_prob),
                     brier=round(float(brier_score_loss(test["is_scam"], test_prob)), 5),
                     **at_threshold(test, test_prob >= alone, test_customers), train_seconds=round(time.time() - started, 1),
                     ms_per_payment=speed(booster.predict, test), size_kb=int(round(len(booster.model_to_string()) / 1024))))

    started = time.time()
    iso, scale = risk.train_isolation(fit)
    valid_anomaly = risk.isolation_scores(iso, scale, valid)
    test_anomaly = risk.isolation_scores(iso, scale, test)
    iso_alone = pick_threshold(valid_anomaly[material_legit(valid)], allowed)
    rows.append(dict(model="Isolation Forest", kind="unsupervised, never sees a scam label", **ranking(test, test_anomaly),
                     brier=None, **at_threshold(test, test_anomaly >= iso_alone, test_customers),
                     train_seconds=round(time.time() - started, 1),
                     ms_per_payment=speed(lambda frame: iso.score_samples(frame.to_numpy(dtype=float)), test),
                     size_kb=pickled_kb(iso)))

    threshold = pick_threshold(valid_prob[material_legit(valid)], int(BEHAVIOUR_BUDGET * customers))
    remaining = material_legit(valid) & (valid_prob < threshold)
    iso_threshold = min(1.0, pick_threshold(valid_anomaly[remaining], int(ISOLATION_BUDGET * customers)))
    combined = (test_prob >= threshold) | (test_anomaly >= iso_threshold)
    rows.append(dict(model="LightGBM + Isolation Forest", kind="behaviour model in production", pr_auc=None, roc_auc=None,
                     scams_at_equal_budget=None, recall_at_equal_budget=None, brier=None,
                     **at_threshold(test, combined, test_customers), train_seconds=None, ms_per_payment=None, size_kb=None))
    only_iso = (test_anomaly >= iso_threshold) & (test_prob < threshold) & (test["amount"].to_numpy() >= MATERIAL_MIN)
    return {
        "protocol": ("Fit on April to July, choose the threshold on August so that every model is allowed the same number "
                     "of false pauses, refit on April to August, score September once."),
        "false_pause_budget_per_customer_month": round(TOTAL_BUDGET, 2),
        "rows": rows,
        "thresholds": {"lightgbm": round(threshold, 4), "isolation": round(iso_threshold, 4)},
        "isolation_only_flags": {"scams": int((only_iso & (test["is_scam"].to_numpy() == 1)).sum()),
                                 "legit": int((only_iso & (test["is_scam"].to_numpy() == 0)).sum())},
        "scores": {"valid_prob": valid_prob, "test_prob": test_prob, "booster": booster, "threshold": threshold,
                   "high": combined, "isolation": iso, "isolation_scale": scale},
    }


def calibration(valid: pd.DataFrame, test: pd.DataFrame, valid_prob: np.ndarray, test_prob: np.ndarray) -> dict[str, Any]:
    fitted = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(valid_prob, valid["is_scam"].astype(int))
    adjusted = fitted.predict(test_prob)
    target = test["is_scam"].to_numpy()

    def table(scores: np.ndarray) -> list[dict[str, Any]]:
        out = []
        for low, high in zip(CALIBRATION_EDGES[:-1], CALIBRATION_EDGES[1:]):
            chosen = (scores >= low) & (scores < high)
            if chosen.sum():
                out.append({"range": f"{low:.2f} to {min(high, 1.0):.2f}", "payments": int(chosen.sum()),
                            "mean_predicted": round(float(scores[chosen].mean()), 4),
                            "observed_scam_rate": round(float(target[chosen].mean()), 4)})
        return out

    def gap(scores: np.ndarray) -> float:
        total = 0.0
        for low, high in zip(CALIBRATION_EDGES[:-1], CALIBRATION_EDGES[1:]):
            chosen = (scores >= low) & (scores < high)
            if chosen.sum():
                total += chosen.sum() / len(scores) * abs(scores[chosen].mean() - target[chosen].mean())
        return round(float(total), 5)

    return {
        "method": "Isotonic regression fitted on the validation month, applied to the test month.",
        "base_rate_test": round(float(target.mean()), 5),
        "brier_raw": round(float(brier_score_loss(target, test_prob)), 5),
        "brier_calibrated": round(float(brier_score_loss(target, adjusted)), 5),
        "brier_always_base_rate": round(float(brier_score_loss(target, np.full(len(target), target.mean()))), 5),
        "expected_calibration_error_raw": gap(test_prob),
        "expected_calibration_error_calibrated": gap(adjusted),
        "raw": table(test_prob), "calibrated": table(adjusted),
        "note": ("Thamun decides with a threshold on the ranking, so calibration does not change any decision. "
                 "The probabilities reflect the scam rate of the simulator, which is far above real life."),
    }


def feature_ablation(fit: pd.DataFrame, valid: pd.DataFrame, train: pd.DataFrame, test: pd.DataFrame) -> dict[str, Any]:
    def measure(features: list[str]) -> dict[str, Any]:
        _, test_prob, _ = boosted(features, fit, valid, train, test)
        return dict(features=len(features), scam_payments=int(test["is_scam"].sum()), **ranking(test, test_prob))

    cumulative, features = [], []
    for group, names in GROUPS.items():
        features = features + names
        cumulative.append(dict(step=("Only " if not cumulative else "+ ") + GROUP_NAMES[group], group=group,
                               **measure(list(features))))
    production = measure(RISK_FEATURES)
    left_out = []
    for group, names in GROUPS.items():
        if group == "payment_fields":
            continue
        kept = [f for f in RISK_FEATURES if f not in names]
        row = measure(kept)
        left_out.append(dict(removed=GROUP_NAMES[group], group=group, **row,
                             pr_auc_change=round(row["pr_auc"] - production["pr_auc"], 4),
                             scams_change=row["scams_at_equal_budget"] - production["scams_at_equal_budget"]))
    return {"model": ("LightGBM alone with the same parameters in every row. Scams caught are counted with each model "
                      f"allowed exactly {TOTAL_BUDGET:.2f} false pauses per customer in the test month, so rows are comparable"),
            "cumulative": cumulative, "production_set": production, "leave_one_group_out": left_out}


def system_ablation(decided: pd.DataFrame, customers: int) -> dict[str, Any]:
    scams = decided[decided.is_scam == 1]
    legit = decided[decided.is_scam == 0]

    def layer(name: str, scam_mask: pd.Series, legit_mask: pd.Series, note: str = "") -> dict[str, Any]:
        return {"layer": name, "scams_paused": int(scam_mask.sum()), "scam_payments": int(len(scams)),
                "recall": evaluate.rate(scam_mask.sum(), len(scams)),
                "genuine_pauses_per_customer_month": evaluate.rate(legit_mask.sum(), customers), "note": note}

    rows = [
        layer("Purpose rules alone", scams.rules, legit.rules, "Needs the customer to answer the purpose question."),
        layer("Behaviour model alone (LightGBM + Isolation Forest)", scams.behaviour, legit.behaviour),
        layer("Behaviour model + purpose rules", scams.behaviour | scams.rules, legit.behaviour | legit.rules),
        layer("+ bill-risk pause (full Thamun decision)", scams.decision == "pause", legit.decision == "pause",
              "The extra pauses are affordability warnings, not scam warnings."),
    ]
    only_rules = scams.rules & ~scams.behaviour
    only_model = scams.behaviour & ~scams.rules
    return {
        "rows": rows,
        "caught_only_by_rules": int(only_rules.sum()), "caught_only_by_model": int(only_model.sum()),
        "caught_by_both": int((scams.rules & scams.behaviour).sum()),
        "purpose_question_share": evaluate.rate(decided.asked.sum(), len(decided)),
        "scam_number_reputation": ("Not measured. In this simulator every scam uses a number once, so a report list "
                                   "cannot help by construction. Its value depends on how often real scammers reuse "
                                   "numbers and how many victims report, which needs real data."),
    }


def unseen_scam_types(fit: pd.DataFrame, valid: pd.DataFrame, train: pd.DataFrame, test: pd.DataFrame,
                      iso: Any, scale: dict[str, float]) -> dict[str, Any]:
    customers = int(valid["customer_id"].nunique())
    test_anomaly = risk.isolation_scores(iso, scale, test)
    material = test["amount"].to_numpy() >= MATERIAL_MIN
    rows = []
    for scam_type in sorted(t for t in test["scam_type"].unique() if t != "none"):
        def without(frame: pd.DataFrame) -> pd.DataFrame:
            return frame[frame["scam_type"] != scam_type]

        seen_valid = without(valid)
        valid_prob, test_prob, _ = boosted(RISK_FEATURES, without(fit), seen_valid, without(train), test)
        threshold = pick_threshold(valid_prob[material_legit(seen_valid)], int(BEHAVIOUR_BUDGET * customers))
        valid_anomaly = risk.isolation_scores(iso, scale, seen_valid)
        remaining = material_legit(seen_valid) & (valid_prob < threshold)
        iso_threshold = min(1.0, pick_threshold(valid_anomaly[remaining], int(ISOLATION_BUDGET * customers)))
        target = (test["scam_type"].to_numpy() == scam_type) & material
        by_model = (test_prob >= threshold) & target
        by_either = ((test_prob >= threshold) | (test_anomaly >= iso_threshold)) & target
        rows.append({"scam_type": scam_type, "payments": int((test["scam_type"] == scam_type).sum()),
                     "caught_by_lightgbm": int(by_model.sum()), "caught_with_isolation_forest": int(by_either.sum()),
                     "added_by_isolation_forest": int(by_either.sum() - by_model.sum()),
                     "recall_lightgbm": evaluate.rate(by_model.sum(), (test["scam_type"] == scam_type).sum()),
                     "recall_combined": evaluate.rate(by_either.sum(), (test["scam_type"] == scam_type).sum())})
    total = sum(r["payments"] for r in rows)
    return {"method": ("For each scam type, every scam of that type is removed from training and validation, so the "
                       "model has never seen it. The table shows how many September payments of that type are still caught."),
            "rows": rows,
            "overall_lightgbm": evaluate.rate(sum(r["caught_by_lightgbm"] for r in rows), total),
            "overall_combined": evaluate.rate(sum(r["caught_with_isolation_forest"] for r in rows), total),
            "added_by_isolation_forest": sum(r["added_by_isolation_forest"] for r in rows)}


def importance(booster: Any, test: pd.DataFrame) -> dict[str, Any]:
    contributions = np.abs(booster.predict(test[RISK_FEATURES], pred_contrib=True)[:, :-1])
    mean = contributions.mean(axis=0)
    total = float(mean.sum())
    by_feature = sorted(zip(RISK_FEATURES, mean), key=lambda kv: -kv[1])
    by_group = {}
    for group, names in GROUPS.items():
        members = [f for f in names if f in RISK_FEATURES]
        by_group[GROUP_NAMES[group]] = round(float(sum(mean[RISK_FEATURES.index(f)] for f in members)) / total, 4)
    return {"method": "Mean absolute SHAP value over every payment in the test month (LightGBM tree SHAP).",
            "features": [{"feature": name, "share": round(float(value) / total, 4)} for name, value in by_feature[:10]],
            "groups": dict(sorted(by_group.items(), key=lambda kv: -kv[1]))}


def drift_reference(test: pd.DataFrame, test_prob: np.ndarray, high: np.ndarray) -> dict[str, Any]:
    counts = np.bincount(np.searchsorted(SCORE_EDGES, test_prob, side="right"), minlength=len(SCORE_EDGES) + 1)
    return {"source": "test month of the synthetic data", "payments": int(len(test_prob)), "score_edges": SCORE_EDGES,
            "score_shares": [round(float(c) / len(test_prob), 6) for c in counts],
            "high_risk_share": round(float(high.mean()), 5)}


def stress(models: dict[str, Any]) -> dict[str, Any]:
    rows = []
    original = (P.MODEST_SCAM_SHARE, P.PURPOSE_HONESTY_SCALE)
    try:
        for variant in STRESS:
            started = time.time()
            P.MODEST_SCAM_SHARE, P.PURPOSE_HONESTY_SCALE = variant["modest"], variant["honesty"]
            with tempfile.TemporaryDirectory() as folder:
                generator.generate(seed=variant["seed"], quiet=True, out_dir=folder)
                txns = load_transactions(Path(folder) / "transactions.csv")
                bills = evaluate.load_bill_events(folder)
            table = evaluate.score_table(build_table(txns), models)
            decided, _, _, _ = evaluate.run(txns, table, bills)
            guard = evaluate.guard_metrics(decided, int(txns["customer_id"].nunique()))
            rows.append({"id": variant["id"], "name": variant["name"], "seed": variant["seed"],
                         "scam_payments": guard["scam_payments"],
                         "scams_paused": int((decided[decided.is_scam == 1].decision == "pause").sum()),
                         "recall": guard["recall_payments"], "recall_interval": guard["recall_payments_interval"],
                         "recall_first_payment": guard["recall_first_payment"], "recall_money": guard["recall_money"],
                         "recall_model_only": guard["recall_model_only"], "recall_rules_only": guard["recall_rules_only"],
                         "false_pauses_per_customer_month": guard["false_pauses_per_customer_month"],
                         "no_interruption": evaluate.friction(decided)["no_interruption"],
                         "seconds": round(time.time() - started, 1)})
            print(f"stress {variant['id']}: recall {guard['recall_payments']} false pauses {guard['false_pauses_per_customer_month']}")
    finally:
        P.MODEST_SCAM_SHARE, P.PURPOSE_HONESTY_SCALE = original
    fresh = [r for r in rows if r["id"].startswith("new_customers")]
    paused, total = sum(r["scams_paused"] for r in fresh), sum(r["scam_payments"] for r in fresh)
    return {
        "method": ("The models and thresholds trained on the main dataset are frozen. Each row is a newly generated "
                   "population that the models never saw, scored on its September. Nothing is retrained or retuned."),
        "rows": rows,
        "new_customers_pooled": {"scam_payments": total, "scams_paused": paused, "recall": evaluate.rate(paused, total),
                                 "recall_interval": evaluate.wilson(paused, total),
                                 "false_pauses_per_customer_month": round(
                                     float(np.mean([r["false_pauses_per_customer_month"] for r in fresh])), 4)},
    }


def pct(value: Optional[float], digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def number(value: Optional[float], digits: int = 3) -> str:
    return "n/a" if value is None else f"{round(value + 1e-9, digits):.{digits}f}"


def report(result: dict[str, Any]) -> str:
    comparison, ablation, system = result["comparison"], result["feature_ablation"], result["system_ablation"]
    cal, shap, lines = result["calibration"], result["importance"], []
    add = lines.append
    add("# Model comparison, ablation and stress test")
    add("")
    add(f"Generated by `python -m ml.experiments` on {result['generated_at']}. Every number below is computed by that "
        "script on synthetic data. Nothing here comes from real customers.")
    add("")
    add("## 1. Which model should pause payments?")
    add("")
    add(comparison["protocol"])
    add(f"Budget: {comparison['false_pause_budget_per_customer_month']} false pauses per customer per month on the "
        "validation month. A pause needs an amount of at least 300 taka.")
    add("")
    add("| Model | PR-AUC | Scams caught at equal budget | Scams caught (threshold from August) | Precision | F1 | False pauses per customer per month | ms per payment | Size |")
    add("|---|---|---|---|---|---|---|---|---|")
    for r in comparison["rows"]:
        equal = "n/a" if r["scams_at_equal_budget"] is None else f"{r['scams_at_equal_budget']} of {r['scam_payments']}"
        size = "n/a" if r["size_kb"] is None else f"{r['size_kb']} KB"
        add(f"| {r['model']} ({r['kind']}) | {number(r['pr_auc'])} | {equal} | "
            f"{r['scams_caught']} of {r['scam_payments']} ({pct(r['recall'])}) | {pct(r['precision'])} | "
            f"{number(r['f1'])} | {number(r['false_pauses_per_customer_month'], 2)} | {number(r['ms_per_payment'], 2)} | {size} |")
    add("")
    add("\"Equal budget\" lets each model make exactly the same number of false pauses in September, which is the fair "
        "way to compare ranking quality. \"Threshold from August\" is what would really have happened, because the "
        "threshold was fixed before September was seen.")
    add("")
    only = comparison["isolation_only_flags"]
    add(f"Inside the combined model the Isolation Forest flags {only['scams']} scam payments and {only['legit']} genuine "
        "payments that LightGBM alone did not flag. Section 5 tests whether it helps on scam types the model was never "
        "trained on.")
    add("")
    add("## 2. Is the scam probability calibrated?")
    add("")
    add(cal["method"] + " " + cal["note"])
    add("")
    add("| | Brier score | Expected calibration error |")
    add("|---|---|---|")
    add(f"| LightGBM raw output | {cal['brier_raw']} | {cal['expected_calibration_error_raw']} |")
    add(f"| After isotonic calibration | {cal['brier_calibrated']} | {cal['expected_calibration_error_calibrated']} |")
    add(f"| Always predicting the base rate ({pct(cal['base_rate_test'], 2)}) | {cal['brier_always_base_rate']} | |")
    add("")
    add("| Score range (calibrated) | Payments | Mean predicted | Observed scam rate |")
    add("|---|---|---|---|")
    for row in cal["calibrated"]:
        add(f"| {row['range']} | {row['payments']} | {pct(row['mean_predicted'])} | {pct(row['observed_scam_rate'])} |")
    add("")
    add("## 3. Which signals carry the result? (feature-group ablation)")
    add("")
    add(ablation["model"] + ".")
    add("")
    add("| Features used | Count | PR-AUC | Scams caught at equal budget | Recall |")
    add("|---|---|---|---|---|")
    for r in ablation["cumulative"]:
        add(f"| {r['step']} | {r['features']} | {number(r['pr_auc'])} | {r['scams_at_equal_budget']} of {r['scam_payments']} | "
            f"{pct(r['recall_at_equal_budget'])} |")
    r = ablation["production_set"]
    add(f"| Production feature set (no raw amount) | {r['features']} | {number(r['pr_auc'])} | "
        f"{r['scams_at_equal_budget']} of {r['scam_payments']} | {pct(r['recall_at_equal_budget'])} |")
    add("")
    add("Leave one group out of the production set:")
    add("")
    add("| Group removed | PR-AUC | Change | Scams caught at equal budget | Change |")
    add("|---|---|---|---|---|")
    for r in ablation["leave_one_group_out"]:
        add(f"| {r['removed']} | {number(r['pr_auc'])} | {r['pr_auc_change']:+.3f} | {r['scams_at_equal_budget']} of "
            f"{r['scam_payments']} | {r['scams_change']:+d} |")
    add("")
    add("## 4. What does each decision layer add? (system ablation)")
    add("")
    add("| Layer | Scam payments paused | Recall | Genuine payments paused per customer per month | Note |")
    add("|---|---|---|---|---|")
    for r in system["rows"]:
        add(f"| {r['layer']} | {r['scams_paused']} of {r['scam_payments']} | {pct(r['recall'])} | "
            f"{number(r['genuine_pauses_per_customer_month'], 2)} | {r['note']} |")
    add("")
    add(f"Caught by both layers: {system['caught_by_both']}. Only by the model: {system['caught_only_by_model']}. "
        f"Only by the purpose rules: {system['caught_only_by_rules']}. The purpose question was asked on "
        f"{pct(system['purpose_question_share'])} of payments.")
    add("")
    add("Scam-number reputation: " + system["scam_number_reputation"])
    add("")
    unseen = result["unseen_scam_types"]
    add("## 5. Does it catch a scam type it was never trained on?")
    add("")
    add(unseen["method"])
    add("")
    add("| Scam type hidden from training | Payments in September | Caught by LightGBM | Caught with Isolation Forest added | Added by Isolation Forest |")
    add("|---|---|---|---|---|")
    for r in unseen["rows"]:
        add(f"| {r['scam_type']} | {r['payments']} | {r['caught_by_lightgbm']} ({pct(r['recall_lightgbm'])}) | "
            f"{r['caught_with_isolation_forest']} ({pct(r['recall_combined'])}) | {r['added_by_isolation_forest']:+d} |")
    add("")
    add(f"Across all hidden types: LightGBM alone {pct(unseen['overall_lightgbm'])}, with the Isolation Forest "
        f"{pct(unseen['overall_combined'])}.")
    add("")
    add("## 6. What moves the score overall? (global SHAP)")
    add("")
    add(shap["method"])
    add("")
    add("| Signal group | Share of total attribution |")
    add("|---|---|")
    for name, share in shap["groups"].items():
        add(f"| {name} | {pct(share)} |")
    add("")
    add("| Feature | Share |")
    add("|---|---|")
    for row in shap["features"]:
        add(f"| {row['feature']} | {pct(row['share'])} |")
    add("")
    if result.get("stress"):
        stress_result = result["stress"]
        add("## 7. Stress test: what if the simulator is wrong?")
        add("")
        add(stress_result["method"])
        add("")
        add("| Population | Scam payments | Paused | Recall (95% interval) | First payment | Model alone | Rules alone | False pauses per customer per month | No interruption |")
        add("|---|---|---|---|---|---|---|---|---|")
        for r in stress_result["rows"]:
            add(f"| {r['name']} | {r['scam_payments']} | {r['scams_paused']} | {pct(r['recall'])} "
                f"({pct(r['recall_interval'][0])} to {pct(r['recall_interval'][1])}) | {pct(r['recall_first_payment'])} | "
                f"{pct(r['recall_model_only'])} | {pct(r['recall_rules_only'])} | "
                f"{number(r['false_pauses_per_customer_month'], 2)} | {pct(r['no_interruption'])} |")
        pooled = stress_result["new_customers_pooled"]
        add("")
        add(f"Pooled over the three new populations: {pooled['scams_paused']} of {pooled['scam_payments']} scam payments "
            f"paused, {pct(pooled['recall'])} (95% interval {pct(pooled['recall_interval'][0])} to "
            f"{pct(pooled['recall_interval'][1])}), with {number(pooled['false_pauses_per_customer_month'], 2)} false "
            "pauses per customer per month.")
        add("")
    add("## Limits")
    add("")
    add("- Training data, test data and stress populations all come from one simulator written by the team. "
        "The stress test changes two assumptions against us, but it cannot replace real transactions.")
    add("- The September test month has few scam payments, so one payment moves recall by about two points. "
        "Read the intervals, not the point values.")
    add("- Scams are injected far more often than in real life. Precision and the calibrated probabilities would be "
        "lower at a real base rate. False pauses per customer per month do not depend on that rate.")
    add("- Performance on real customers is not yet measured. The validation roadmap is in `docs/validation_roadmap.md`.")
    add("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="skip the stress test")
    args = parser.parse_args()
    started = time.time()
    txns = load_transactions(DATA / "transactions.csv")
    table = build_table(txns)
    fit, valid, train, test = split(table)
    print(f"rows fit={len(fit)} valid={len(valid)} train={len(train)} test={len(test)}")

    comparison = compare_models(fit, valid, train, test)
    scores = comparison.pop("scores")
    print("model comparison done")
    result: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "label": "Synthetic evaluation",
        "data": {"test_month": str(P.TEST_START)[:7], "test_payments": int(len(test)),
                 "test_scam_payments": int(test["is_scam"].sum()), "customers": int(test["customer_id"].nunique())},
        "comparison": comparison,
        "calibration": calibration(valid, test, scores["valid_prob"], scores["test_prob"]),
        "feature_ablation": feature_ablation(fit, valid, train, test),
        "unseen_scam_types": unseen_scam_types(fit, valid, train, test, scores["isolation"], scores["isolation_scale"]),
        "importance": importance(scores["booster"], test),
    }
    print("ablation done")
    models = evaluate.load_models()
    decided, _, _, _ = evaluate.run(txns, evaluate.score_table(table, models), evaluate.load_bill_events())
    result["system_ablation"] = system_ablation(decided, int(txns["customer_id"].nunique()))
    result["stress"] = None if args.quick else stress(models)
    result["seconds"] = round(time.time() - started, 1)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "experiments.json").write_text(json.dumps(result, indent=2))
    (EVIDENCE / "reference.json").write_text(json.dumps(drift_reference(test, scores["test_prob"], scores["high"]), indent=2))
    DOCS.mkdir(exist_ok=True)
    (DOCS / "model_comparison.md").write_text(report(result))
    print(report(result))


if __name__ == "__main__":
    main()
