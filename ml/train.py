import json
import platform
from datetime import datetime
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import sklearn

from data.personas import CATEGORIES, TEST_START, VALID_START
from ml import categorizer, risk
from ml.features import CAT_FEATURES, RISK_FEATURES, build_table, load_transactions

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "out"
MODELS = ROOT / "ml" / "models"

TARGET_AUTO_ACCURACY = 0.97
BEHAVIOUR_BUDGET = 0.4
ISOLATION_BUDGET = 0.08
MATERIAL_MIN = 300


def split(table):
    ts = pd.to_datetime(table["ts"])
    fit = table[ts < pd.Timestamp(VALID_START)]
    valid = table[(ts >= pd.Timestamp(VALID_START)) & (ts < pd.Timestamp(TEST_START))]
    train = table[ts < pd.Timestamp(TEST_START)]
    test = table[ts >= pd.Timestamp(TEST_START)]
    return fit, valid, train, test


def pick_confidence(correct, confidence):
    for threshold in np.arange(0.5, 0.96, 0.05):
        chosen = confidence >= threshold
        if chosen.sum() and correct[chosen].mean() >= TARGET_AUTO_ACCURACY:
            return float(round(threshold, 2))
    return 0.95


def pick_threshold(scores, allowed):
    ordered = np.sort(scores)[::-1]
    if allowed >= len(ordered):
        return 0.0
    return float(ordered[allowed]) + 1e-9


def main():
    MODELS.mkdir(parents=True, exist_ok=True)
    txns = load_transactions(DATA / "transactions.csv")
    print(f"building features for {len(txns)} transactions")
    table = build_table(txns)
    table.to_csv(DATA / "features.csv", index=False)
    fit, valid, train, _ = split(table)
    customers = valid["customer_id"].nunique()

    cat_fit, cat_rounds = categorizer.train(fit, valid)
    predicted, confidence = categorizer.predict_table(cat_fit, valid)
    correct = predicted == categorizer.labels_of(valid)
    cat_threshold = pick_confidence(correct, confidence)
    cat_final, _ = categorizer.train(train, rounds=cat_rounds)
    cat_final.save_model(str(MODELS / categorizer.MODEL_FILE))
    print(f"categorizer: rounds={cat_rounds} valid accuracy={correct.mean():.3f} threshold={cat_threshold}")

    risk_fit, risk_rounds = risk.train_booster(fit, valid)
    prob = risk_fit.predict(valid[RISK_FEATURES])
    legit = (valid["is_scam"].to_numpy() == 0) & (valid["amount"].to_numpy() >= MATERIAL_MIN)
    threshold = pick_threshold(prob[legit], int(BEHAVIOUR_BUDGET * customers))
    iso, scale = risk.train_isolation(fit)
    anomaly = risk.isolation_scores(iso, scale, valid)
    remaining = legit & (prob < threshold)
    iso_threshold = min(1.0, pick_threshold(anomaly[remaining], int(ISOLATION_BUDGET * customers)))
    scams = valid["is_scam"].to_numpy() == 1
    caught = scams & ((prob >= threshold) | (anomaly >= iso_threshold))
    print(f"risk: rounds={risk_rounds} threshold={threshold:.4f} iso_threshold={iso_threshold:.4f} "
          f"valid scam recall={caught.sum() / max(scams.sum(), 1):.3f}")

    risk_final, _ = risk.train_booster(train, rounds=risk_rounds)
    risk_final.save_model(str(MODELS / risk.MODEL_FILE))
    iso.set_params(n_jobs=None)
    joblib.dump(iso, MODELS / risk.ISO_FILE)

    meta = {
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "versions": {"python": platform.python_version(), "lightgbm": lgb.__version__, "scikit_learn": sklearn.__version__,
                     "numpy": np.__version__, "pandas": pd.__version__},
        "data": {"fit_rows": int(len(fit)), "valid_rows": int(len(valid)), "train_rows": int(len(train)),
                 "train_scams": int(train["is_scam"].sum()), "valid_customers": int(customers)},
        "categories": CATEGORIES,
        "categorizer": {"features": CAT_FEATURES, "rounds": int(cat_rounds), "threshold": cat_threshold,
                        "valid_accuracy": float(correct.mean())},
        "risk": {"features": RISK_FEATURES, "rounds": int(risk_rounds), "threshold": threshold,
                 "iso_threshold": iso_threshold, "iso_scale": scale,
                 "valid_recall": float(caught.sum() / max(scams.sum(), 1))},
    }
    (MODELS / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"saved models to {MODELS}")


if __name__ == "__main__":
    main()
