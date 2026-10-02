import json
from pathlib import Path

import lightgbm as lgb
import numpy as np

from data.personas import CATEGORIES
from ml.features import CAT_CATEGORICAL, CAT_FEATURES

MODEL_FILE = "categorizer.txt"

PARAMS = {
    "objective": "multiclass",
    "num_class": len(CATEGORIES),
    "learning_rate": 0.08,
    "num_leaves": 31,
    "min_data_in_leaf": 20,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": 42,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 2,
    "verbose": -1,
}


def labels_of(table):
    return table["category"].map({c: i for i, c in enumerate(CATEGORIES)}).astype(int).to_numpy()


def train(fit, valid=None, rounds=None):
    data = lgb.Dataset(fit[CAT_FEATURES], label=labels_of(fit), categorical_feature=CAT_CATEGORICAL, free_raw_data=False)
    if valid is not None:
        held = lgb.Dataset(valid[CAT_FEATURES], label=labels_of(valid), reference=data)
        booster = lgb.train(PARAMS, data, num_boost_round=400, valid_sets=[held],
                            callbacks=[lgb.early_stopping(30, verbose=False)])
        return booster, booster.best_iteration
    return lgb.train(PARAMS, data, num_boost_round=rounds), rounds


def predict_table(booster, table):
    probs = booster.predict(table[CAT_FEATURES])
    return probs.argmax(axis=1), probs.max(axis=1)


class Categorizer:
    def __init__(self, booster, threshold):
        self.booster = booster
        self.threshold = threshold

    @classmethod
    def load(cls, folder):
        folder = Path(folder)
        meta = json.loads((folder / "meta.json").read_text())
        return cls(lgb.Booster(model_file=str(folder / MODEL_FILE)), meta["categorizer"]["threshold"])

    def predict(self, feats):
        row = np.array([[feats[name] for name in CAT_FEATURES]], dtype=float)
        probs = self.booster.predict(row)[0]
        order = np.argsort(probs)[::-1]
        return {
            "label": CATEGORIES[int(order[0])],
            "confidence": float(probs[order[0]]),
            "confident": bool(probs[order[0]] >= self.threshold),
            "alternatives": [{"label": CATEGORIES[int(i)], "confidence": float(probs[i])} for i in order[1:3]],
        }
