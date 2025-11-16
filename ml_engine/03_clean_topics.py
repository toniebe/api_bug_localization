#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_clean_topics.py
- Clean topics.csv by removing noise tokens and assigning human-friendly labels
- Join labels into bugs_with_topics.csv → bugs_with_labels.csv

Usage:
  python 03_clean_topics.py     --topics out_lda/topics.csv     --bugs out_lda/bugs_with_topics.csv     --outdir out_lda     [--labels_json topic_labels.json]     [--extra_noise "foo,bar,baz"]

Notes:
- If --labels_json is provided, it should contain: {"0": "Label for topic 0", "1": "...", ...}
- If labels are not provided, script auto-generates labels from clean terms with simple heuristics.
"""

import os, argparse, json

import pandas as pd

DEFAULT_NOISE = {
    # generic words
    "add","added","adding","use","using","used","set","new","default","tools","tool",
    "support","consider","code",
    # bug words
    "error","issue","bug","crash","fail","failed","failure","failures","invalid","message",
    "intermittent","regression","tracking","single","tier",
    # testing
    "test","tests","testing","wpt","assertion","timeout","unexpected","perma","permafailing",
    # org/vendor
    "mozilla","org","com","java","lang",
    # ui-generic
    "page","window","windows","button","menu","tab","tabs","toolbar","screen","view",
    # digits/versions and similar tokens (handled via heuristic below)
    "version","task","meta","update",
    # very generic
    "file","files","value","property","process","working","properly","correctly",
}

def parse_list(s: str):
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]

def clean_terms(term_str: str, extra_noise=None) -> str:
    noise = set(DEFAULT_NOISE)
    if extra_noise:
        noise |= {t.lower() for t in extra_noise}
    words = [w.strip() for w in str(term_str).split(",")]
    cleaned = []
    for w in words:
        lw = w.lower()
        if lw in noise:
            continue
        # drop tokens containing digits or shorter than 3
        if any(ch.isdigit() for ch in lw):
            continue
        if len(lw) < 3:
            continue
        cleaned.append(lw)
    # de-duplicate preserving order
    seen, out = set(), []
    for w in cleaned:
        if w not in seen:
            out.append(w); seen.add(w)
    return ", ".join(out)

def auto_label_from_terms(clean_terms: str) -> str:
    terms = [t.strip() for t in clean_terms.split(",") if t.strip()]
    s = set(terms)
    if {"autofill","address","form","password","email"} & s:
        return "Forms / Email / Autofill"
    if {"tab","window","menu","open"} & s:
        return "UI: Tabs & Windows"
    if {"pdf","android","toolbar","screen","view"} & s:
        return "UI: Toolbar / PDF / Android"
    if {"css","html","anchor","position"} & s:
        return "HTML/CSS Rendering"
    if {"intermittent","timeout","worker"} & s:
        return "Test Automation / Intermittent"
    if {"search","history","telemetry","browser"} & s:
        return "Search / Telemetry / History"
    if {"cors","font","resource","load"} & s:
        return "Web Resource / CORS"
    return " / ".join(terms[:3]) if terms else "Misc"

def load_labels_json(path: str):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    labels = {}
    for k, v in raw.items():
        try:
            ki = int(k)
        except Exception:
            continue
        labels[ki] = v
    return labels

def main():
    ap = argparse.ArgumentParser(description="Clean topics and label them; join labels into bugs file")
    ap.add_argument("--project", type=str, default="idnproject", help="Name of Project")
    ap.add_argument("--topics", type=str, default="out_lda/idnproject/topics.csv", help="Path to topics.csv")
    ap.add_argument("--bugs", type=str, default="out_lda/idnproject/bugs_with_topics.csv", help="Path to bugs_with_topics.csv")
    ap.add_argument("--outdir", type=str, default="out_lda/idnproject", help="Output directory")
    ap.add_argument("--labels_json", type=str, default=None, help="Optional JSON mapping {topic_id: label}")
    ap.add_argument("--extra_noise", type=str, default=None, help="Comma-separated extra noise tokens")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # Load topics
    topics = pd.read_csv(args.topics)
    if "topic_id" not in topics.columns or "terms" not in topics.columns:
        raise ValueError("topics.csv must contain columns: topic_id, terms")

    extra_noise = parse_list(args.extra_noise)
    topics["clean_terms"] = topics["terms"].apply(lambda s: clean_terms(str(s), extra_noise))

    # Labels
    user_labels = load_labels_json(args.labels_json)
    labels = []
    for _, row in topics.iterrows():
        tid = int(row["topic_id"])
        if tid in user_labels:
            labels.append(user_labels[tid])
        else:
            labels.append(auto_label_from_terms(row["clean_terms"]))
    topics["topic_label"] = labels

    out_topics = os.path.join(args.outdir, "topics_cleaned.csv")
    topics.to_csv(out_topics, index=False)
    print(f"[CLEAN] Wrote {out_topics}")

    # Load bugs and merge labels
    bugs = pd.read_csv(args.bugs)
    if "dominant_topic" not in bugs.columns:
        raise ValueError("bugs_with_topics.csv must contain 'dominant_topic' column")

    merged = bugs.merge(
        topics[["topic_id", "topic_label"]],
        left_on="dominant_topic",
        right_on="topic_id",
        how="left"
    )
    merged["topic_label"] = merged["topic_label"].fillna("Unknown")

    out_bugs = os.path.join(args.outdir, "bugs_with_labels.csv")
    merged.to_csv(out_bugs, index=False)
    print(f"[CLEAN] Wrote {out_bugs}")

    # Summary
    summary = merged["topic_label"].value_counts(dropna=False).reset_index()
    summary.columns = ["topic_label", "num_bugs"]
    print("[CLEAN] Bug distribution by labeled topic:")
    print(summary.to_string(index=False))

if __name__ == "__main__":
    main()
