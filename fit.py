import math
import random
import re

MIN_EACH = 20
MAX_TERMS = 5000
TEXT_CHARS = 20000
WORD = re.compile(r"[a-z][a-z0-9+#]*")


def features(title, text):
    """Words and word pairs of the title and description; title words also count on their own."""
    out = set()
    for prefix, s in (("t:", title or ""), ("", (text or "")[:TEXT_CHARS])):
        words = WORD.findall(s.lower())
        out |= set(words) | {f"{a} {b}" for a, b in zip(words, words[1:])}
        if prefix:
            out |= {prefix + w for w in words}
    return out


def train(lessons, epochs=5, rate=0.01, l2=1e-4):
    """Logistic regression over (title, text, +1 or -1) lessons, or None until there are enough of each."""
    good = sum(1 for *_, y in lessons if y > 0)
    bad = len(lessons) - good
    if good < MIN_EACH or bad < MIN_EACH:
        return None
    rows = [(features(t, x), 1.0 if y > 0 else 0.0) for t, x, y in lessons]
    seen = {}
    for fs, _ in rows:
        for term in fs:
            seen[term] = seen.get(term, 0) + 1
    rows = [([t for t in fs if seen[t] > 1], y) for fs, y in rows]
    w, b = {}, 0.0
    order = list(range(len(rows)))
    random.Random(0).shuffle(order)
    for _ in range(epochs):
        for i in order:
            fs, y = rows[i]
            z = b + sum(w.get(t, 0.0) for t in fs)
            err = 1 / (1 + math.exp(-max(min(z, 30), -30))) - y
            b -= rate * err
            for t in fs:
                w[t] = w.get(t, 0.0) * (1 - rate * l2) - rate * err
    top = sorted(w.items(), key=lambda kv: abs(kv[1]), reverse=True)[:MAX_TERMS]
    return {"w": {t: round(v, 4) for t, v in top}, "b": round(b, 4), "good": good, "bad": bad}


def score(model, title, text):
    if not model:
        return None
    z = model["b"] + sum(model["w"].get(t, 0.0) for t in features(title, text))
    return 1 / (1 + math.exp(-max(min(z, 30), -30)))


def label(model, title, text):
    p = score(model, title, text)
    if p is None:
        return "learning, no score yet"
    n = model["good"] + model["bad"]
    return f"{round(p * 100)}% ({'title only, ' if not text else ''}learned from {n} reactions)"
