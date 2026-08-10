"""Train the TF-IDF + Logistic Regression intent classifier (Capstone 2 stretch objective).

Loads data/intent_training_data.json (built by generate_intent_dataset.py),
does a stratified train/test split, fits a scikit-learn pipeline, evaluates
it, and saves the fitted pipeline to data/intent_classifier.pkl.

Also runs the original keyword classifier (agents/intent_classifier_keyword.py)
over the same held-out test set so the report has a direct accuracy comparison.

Run: python data/train_intent_classifier.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from agents.intent_classifier_keyword import classify_intent as keyword_classify

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(_DIR, "intent_training_data.json")
MODEL_PATH = os.path.join(_DIR, "intent_classifier.pkl")

TEST_SIZE = 0.15
RANDOM_STATE = 42
LABELS = ["doc_lookup", "kpi_compute", "sql_query"]


def load_dataset() -> tuple[list[str], list[str]]:
    """Read the generated dataset into parallel (questions, intents) lists."""
    rows = json.load(open(DATA_PATH))
    return [r["question"] for r in rows], [r["intent"] for r in rows]


def build_pipeline() -> Pipeline:
    """TF-IDF (word 1-2 grams) + multinomial Logistic Regression — small, fast, interpretable."""
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), lowercase=True, min_df=2)),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])


def keyword_baseline_accuracy(questions: list[str], true_labels: list[str]) -> float:
    """Run the current keyword-rule classifier over the same test set for comparison."""
    preds = [keyword_classify({"question": q})["intent"] for q in questions]
    return accuracy_score(true_labels, preds)


def main() -> None:
    questions, labels = load_dataset()
    x_train, x_test, y_train, y_test = train_test_split(
        questions, labels, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=labels,
    )
    print(f"Train: {len(x_train)}  Test: {len(x_test)}")

    pipeline = build_pipeline()
    pipeline.fit(x_train, y_train)

    y_pred = pipeline.predict(x_test)
    ml_acc = accuracy_score(y_test, y_pred)

    print(f"\nML classifier accuracy: {ml_acc:.3f}")
    print(classification_report(y_test, y_pred, labels=LABELS))
    print("Confusion matrix (rows=true, cols=pred), order:", LABELS)
    print(confusion_matrix(y_test, y_pred, labels=LABELS))

    kw_acc = keyword_baseline_accuracy(x_test, y_test)
    print(f"\nKeyword-rule baseline accuracy on the same test set: {kw_acc:.3f}")
    print(f"ML vs keyword: {ml_acc:.3f} vs {kw_acc:.3f} ({'+' if ml_acc >= kw_acc else ''}{(ml_acc - kw_acc):.3f})")

    joblib.dump(pipeline, MODEL_PATH)
    print(f"\nSaved trained pipeline to {MODEL_PATH}")


if __name__ == "__main__":
    main()
