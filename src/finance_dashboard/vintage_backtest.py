"""Reproducible walk-forward ALFRED recession research, never a live forecast.

At historical origin t, features come from the ALFRED vintages effective at t.
Only recession labels present in the USREC vintage effective at t may enter
training. Outcomes for evaluation are read from the last stored USREC vintage.
Overlapping 6/12-month outcomes create dependence; reported scores are descriptive.
"""
from __future__ import annotations

from datetime import date
from math import exp, log, sqrt
from pathlib import Path

from .vintage import read_snapshot, latest_asof_reading

FEATURES = ("T10Y3M", "SAHMREALTIME")
TARGET = "USREC"
HORIZONS = (6, 12)
VERSION = "alfred_l2_logit_1"
MIN_TRAIN = 60
MIN_TRAIN_EVENTS = 5
MIN_TEST = 24
MIN_TEST_EVENTS = 5
MIN_TEST_NON_EVENTS = 12


def _month(day: date) -> int:
    return day.year * 12 + day.month - 1


def _labels(snapshot: dict) -> dict[int, int]:
    result = {}
    for row in snapshot["observations"]:
        n = int(float(row["value"]))
        if float(row["value"]) not in (0.0, 1.0):
            raise ValueError("USREC label outside {0,1}")
        result[_month(date.fromisoformat(row["date"]))] = n
    return result


def target_after(origin: date, labels: dict[int, int], horizon: int) -> int | None:
    window = [labels.get(_month(origin) + offset) for offset in range(1, horizon+1)]
    return int(any(window)) if all(v in (0, 1) for v in window) else None


def sigmoid(x: float) -> float:
    return 1.0 / (1 + exp(-max(-35.0, min(35.0, x))))


def solve3(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    a = [matrix[i][:] + [rhs[i]] for i in range(3)]
    for i in range(3):
        k = max(range(i, 3), key=lambda j: abs(a[j][i]))
        if abs(a[k][i]) < 1e-10:
            raise ValueError("Singular design")
        a[i], a[k] = a[k], a[i]
        factor = a[i][i]
        for j in range(i, 4):
            a[i][j] /= factor
        for k in range(3):
            if k == i:
                continue
            factor = a[k][i]
            for j in range(i, 4):
                a[k][j] -= factor * a[i][j]
    return [a[i][3] for i in range(3)]


def fit_predict(train: list[tuple[date, tuple[float, float], int]],
                current: tuple[float, float]) -> tuple[float, float]:
    labels = [case[2] for case in train]
    if (len(train) < MIN_TRAIN or sum(labels) < MIN_TRAIN_EVENTS
        or len(labels) - sum(labels) < 24):
        raise ValueError("Insufficient source-confirmed training cases")
    means = [sum(case[1][j] for case in train) / len(train) for j in range(2)]
    stds = [sqrt(sum((case[1][j] - means[j])**2 for case in train)/len(train))
            for j in range(2)]
    if min(stds) < 1e-9:
        raise ValueError("Source feature has no variance")
    rows = [(1.0, (case[1][0]-means[0])/stds[0],
             (case[1][1]-means[1])/stds[1]) for case in train]
    prior = min(.99999, max(.00001, sum(labels)/len(labels)))
    beta = [log(prior/(1-prior)), 0.0, 0.0]
    for _ in range(40):
        gradient, hessian = [0.0]*3, [[0.0]*3 for _ in range(3)]
        for x, y in zip(rows, labels):
            p = sigmoid(sum(a*b for a, b in zip(beta, x)))
            w = max(p*(1-p), 1e-7)
            for i in range(3):
                gradient[i] += (p-y)*x[i]
                for j in range(3):
                    hessian[i][j] += w*x[i]*x[j]
        for j in (1, 2):
            gradient[j] += beta[j]   # Fixed, pre-specified L2 penalty = 1.
            hessian[j][j] += 1.0
        delta = solve3(hessian, gradient)
        beta = [a-b for a,b in zip(beta,delta)]
        if max(abs(v) for v in delta) < 1e-7:
            break
    x = (1.0, (current[0]-means[0])/stds[0],
         (current[1]-means[1])/stds[1])
    return sigmoid(sum(a*b for a,b in zip(beta,x))), prior


def metrics(observations: list[dict]) -> dict | None:
    labels = [p["outcome"] for p in observations]
    positives = sum(labels)
    negatives = len(labels)-positives
    if len(labels) < MIN_TEST or positives < MIN_TEST_EVENTS or negatives < MIN_TEST_NON_EVENTS:
        return None
    scores = [p["estimated_probability"] for p in observations]
    base = [p["past_prevalence_baseline"] for p in observations]
    brier = sum((p-y)**2 for p,y in zip(scores,labels))/len(labels)
    brier0 = sum((p-y)**2 for p,y in zip(base,labels))/len(labels)
    positive = [p for p,y in zip(scores,labels) if y]
    negative = [p for p,y in zip(scores,labels) if not y]
    auc = sum(1 if p>n else .5 if p==n else 0
              for p in positive for n in negative)/(len(positive)*len(negative))
    bins = []
    for i in range(5):
        pairs = [(score,y) for score,y in zip(scores,labels)
                 if i/5 <= score < (i+1)/5 or (i==4 and score==1)]
        bins.append({"range": [i/5, (i+1)/5], "count": len(pairs),
                     "observed_fraction": round(sum(y for _,y in pairs)/len(pairs),6)
                     if pairs else None})
    return {"cases":len(labels),"positives":positives,"negatives":negatives,
            "brier":round(brier,6),"expanding_prevalence_brier":round(brier0,6),
            "brier_skill":round(1-brier/brier0,6) if brier0>0 else None,
            "roc_auc":round(auc,6), "calibration":bins}


def independent_holdout_diagnostics(observations: list[dict], horizon: int) -> dict:
    """Audit horizon overlap and approximate positive-event clustering.

    The original full-month evaluation remains available. This secondary
    pre-specified chronological subsample avoids shared future-label months,
    but is not independently calibrated prospective model validation.
    """
    positives = sorted(_month(date.fromisoformat(row["asof"]))
                       for row in observations if row["outcome"] == 1)
    episodes, previous = 0, None
    for month in positives:
        if previous is None or month - previous > horizon:
            episodes += 1
        previous = month
    selected, last = [], None
    for row in sorted(observations, key=lambda item: item["asof"]):
        month = _month(date.fromisoformat(row["asof"]))
        if last is None or month - last >= horizon:
            selected.append(row)
            last = month
    return {
        "positive_event_episodes_approx": episodes,
        "nonoverlapping_test_cases": len(selected),
        "nonoverlapping_evaluation": metrics(selected),
        "validation_status": "not_independently_validated",
        "selection": "chronological_first_then_every_horizon_months",
        "limitation": ("An event cluster groups overlapping positive future "
                       "outcomes, not independently dated NBER recession cycles. "
                       "Nonoverlapping evaluation reduces shared outcome months "
                       "but does not remove serial correlation, hindsight dating "
                       "or provide external prospective validation."),
    }


def walk_forward(root: Path, *, horizon: int=12) -> dict:
    if horizon not in HORIZONS:
        raise ValueError("Only pre-specified 6 and 12 month evaluation horizons supported")
    result = {
        "status":"insufficient_vintages", "version":VERSION,
        "horizon_months":horizon, "observations":[], "evaluation":None,
        "independence": independent_holdout_diagnostics([], horizon),
        "input_series":[*FEATURES,TARGET],
        "interpretation":("Retrospectively evaluated, as-of ALFRED macro features and "
                          "as-of available training labels; not an independently "
                          "validated current recession probability."),
        "limitations":("NBER USREC recessions are dated retrospectively, and "
                        "consecutive future-year outcome windows overlap. "
                        "Evaluation uses later documented labels; daily market "
                        "prices and future source revisions are never used as "
                        "historical training features. No inferred confidence "
                        "interval or causal interpretation."),
    }
    paths = [root / sid for sid in (*FEATURES,TARGET)]
    if not all(x.exists() for x in paths):
        return result
    stamps = [set(p.stem for p in folder.glob("????-??-??.json")) for folder in paths]
    common = sorted(set.intersection(*stamps))
    records = []
    for token in common:
        try:
            day = date.fromisoformat(token)
            inputs = [read_snapshot(root,sid,day) for sid in FEATURES]
            outcome = read_snapshot(root,TARGET,day)
            if any(item is None for item in inputs) or outcome is None:
                continue
            features = [latest_asof_reading(item) for item in inputs]
            if any(item is None for item in features):
                continue
            records.append((day, (float(features[0]["value"]),
                                  float(features[1]["value"])), _labels(outcome)))
        except (ValueError, KeyError, OSError):
            continue
    result["valid_source_dates"] = len(records)
    if not records:
        return result
    final = records[-1][2]
    for i,(origin,values,_known_at_origin) in enumerate(records):
        # Label availability is controlled by USREC as known at THIS origin;
        # never the final hindsight-labelled series used for evaluation.
        labels_as_known = records[i][2]
        training = []
        for old_date,old_values,_ in records[:i]:
            label = target_after(old_date, labels_as_known, horizon)
            if label is not None:
                training.append((old_date,old_values,label))
        try:
            prob,baseline = fit_predict(training,values)
        except ValueError:
            continue
        truth = target_after(origin,final,horizon)
        if truth is None:
            continue  # Right-censored event windows never become zeros.
        result["observations"].append({
            "asof":origin.isoformat(),"term_spread_pp":values[0],
            "sahm_pp":values[1],
            "estimated_probability":round(prob,6),
            "past_prevalence_baseline":round(baseline,6),
            "training_cases":len(training),"training_positive":sum(t[2] for t in training),
            "last_training_origin":training[-1][0].isoformat(),
            "outcome":truth})
    result["evaluation"] = metrics(result["observations"])
    result["independence"] = independent_holdout_diagnostics(
        result["observations"], horizon)
    if result["evaluation"] is not None:
        result["status"] = "retrospective_evaluated"
    else:
        result["status"] = "insufficient_holdout_events"
    return result
