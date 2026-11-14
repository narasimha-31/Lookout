import json
import random
import time

import fit


def test_features_title_prefix_and_bigrams():
    f = fit.features("Data Analyst", "SQL and Power BI")
    assert {"t:data", "data analyst", "power bi", "sql"} <= f


def test_long_text_is_cut():
    start = time.time()
    f = fit.features("x", "a " * 60000)
    assert time.time() - start < 1 and len(f) < 10


def lessons(n_good, n_bad):
    good = [("Data Analyst", f"build power bi dashboards with sql {i}", 1) for i in range(n_good)]
    bad = [("Research Engineer", f"phd physics research magnetic modeling {i}", -1) for i in range(n_bad)]
    return good + bad


def test_train_needs_twenty_each():
    assert fit.train(lessons(19, 30)) is None


def test_learns_separable_words():
    model = fit.train(lessons(30, 30))
    assert fit.score(model, "Analyst", "power bi dashboards") > 0.7
    assert fit.score(model, "Engineer", "phd physics modeling") < 0.3


def test_model_is_small():
    random.seed(1)
    words = [f"w{i}" for i in range(3000)]
    rows = [("t", " ".join(random.choices(words, k=400)), 1 if i % 2 else -1) for i in range(60)]
    model = fit.train(rows)
    assert len(model["w"]) <= 5000 and len(json.dumps(model)) < 1_000_000


def test_label_texts():
    model = fit.train(lessons(30, 30))
    assert fit.label(None, "t", "x") == "learning, no score yet"
    assert "title only" in fit.label(model, "Data Analyst", "")
    assert fit.label(model, "Data Analyst", "power bi").endswith("(learned from 60 reactions)")
