import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
from sklearn.ensemble import IsolationForest

from ml.features import RISK_CATEGORICAL, RISK_FEATURES

MODEL_FILE = "risk.txt"
ISO_FILE = "isolation_forest.pkl"

PARAMS = {
    "objective": "binary",
    "learning_rate": 0.05,
    "num_leaves": 15,
    "min_data_in_leaf": 15,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "lambda_l2": 2.0,
    "scale_pos_weight": 12.0,
    "seed": 42,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 2,
    "verbose": -1,
}

REASON_FEATURES = {
    "amount_vs_usual": ["amt_ratio_type", "amt_pct", "amt_pct_type", "amt_ratio_max"],
    "new_recipient": ["is_new_cp", "cp_count"],
    "recent_recipient": ["cp_age_days"],
    "balance_share": ["balance_share"],
    "unusual_time": ["hour", "hour_share", "is_night"],
    "rapid_sequence": ["n_1h", "sum_1h_ratio", "mins_since_last", "n_24h", "sum_24h_ratio"],
    "several_new_recipients": ["new_cp_24h"],
}


def train_booster(fit, valid=None, rounds=None):
    data = lgb.Dataset(fit[RISK_FEATURES], label=fit["is_scam"].astype(int), categorical_feature=RISK_CATEGORICAL, free_raw_data=False)
    if valid is not None:
        held = lgb.Dataset(valid[RISK_FEATURES], label=valid["is_scam"].astype(int), reference=data)
        booster = lgb.train(PARAMS, data, num_boost_round=500, valid_sets=[held],
                            callbacks=[lgb.early_stopping(40, verbose=False)])
        return booster, booster.best_iteration
    return lgb.train(PARAMS, data, num_boost_round=rounds), rounds


def train_isolation(fit):
    legit = fit[fit["is_scam"] == 0]
    sample = legit.sample(n=min(len(legit), 40000), random_state=42)
    model = IsolationForest(n_estimators=200, max_samples=512, contamination="auto", random_state=42, n_jobs=2)
    model.fit(sample[RISK_FEATURES].to_numpy(dtype=float))
    raw = -model.score_samples(sample[RISK_FEATURES].to_numpy(dtype=float))
    scale = {"low": float(np.quantile(raw, 0.5)), "high": float(np.quantile(raw, 0.9995))}
    return model, scale


def isolation_scores(model, scale, table):
    raw = -model.score_samples(table[RISK_FEATURES].to_numpy(dtype=float))
    return np.clip((raw - scale["low"]) / max(scale["high"] - scale["low"], 1e-9), 0.0, 1.0)


def facts(feats):
    out = {}
    if feats["amt_ratio_type"] >= 2.0 and feats["n_out"] >= 5:
        out["amount_vs_usual"] = {"ratio": round(feats["amt_ratio_type"], 1), "usual": int(round(feats["usual_amount"]))}
    if feats["is_new_cp"]:
        out["new_recipient"] = {}
    elif feats["cp_age_days"] < 1.0 and feats["cp_count"] <= 3:
        out["recent_recipient"] = {"count": int(feats["cp_count"])}
    if feats["balance_share"] >= 0.6:
        out["balance_share"] = {"pct": int(round(min(feats["balance_share"], 1.0) * 100))}
    if feats["is_night"] or (feats["hour_share"] < 0.012 and feats["n_out"] >= 50):
        out["unusual_time"] = {"hour": int(feats["hour"])}
    if feats["n_1h"] >= 2:
        out["rapid_sequence"] = {"count": int(feats["n_1h"]) + 1}
    if feats["new_cp_24h"] >= 1 and feats["is_new_cp"]:
        out["several_new_recipients"] = {"count": int(feats["new_cp_24h"]) + 1}
    return out


class RiskModel:
    def __init__(self, booster, iso, meta):
        self.booster = booster
        self.iso = iso
        self.scale = meta["iso_scale"]
        self.threshold = meta["threshold"]
        self.iso_threshold = meta["iso_threshold"]

    @classmethod
    def load(cls, folder):
        folder = Path(folder)
        meta = json.loads((folder / "meta.json").read_text())["risk"]
        return cls(lgb.Booster(model_file=str(folder / MODEL_FILE)), joblib.load(folder / ISO_FILE), meta)

    def score(self, feats):
        row = np.array([[feats[name] for name in RISK_FEATURES]], dtype=float)
        prob = float(self.booster.predict(row)[0])
        contrib = self.booster.predict(row, pred_contrib=True)[0][:-1]
        raw = float(-self.iso.score_samples(row)[0])
        iso = float(np.clip((raw - self.scale["low"]) / max(self.scale["high"] - self.scale["low"], 1e-9), 0.0, 1.0))
        by_feature = dict(zip(RISK_FEATURES, (float(c) for c in contrib)))
        true_facts = facts(feats)
        reasons = []
        for code, names in REASON_FEATURES.items():
            if code in true_facts:
                weight = sum(max(by_feature[n], 0.0) for n in names)
                reasons.append(dict(true_facts[code], code=code, weight=round(weight, 3)))
        reasons.sort(key=lambda r: r["weight"], reverse=True)
        top = sorted(by_feature.items(), key=lambda kv: abs(kv[1]), reverse=True)[:6]
        return {
            "probability": prob,
            "anomaly": iso,
            "high": bool(prob >= self.threshold or iso >= self.iso_threshold),
            "reasons": reasons,
            "contributions": [{"feature": k, "value": round(float(feats[k]), 3), "shap": round(v, 3)} for k, v in top],
        }
