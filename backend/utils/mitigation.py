# backend/utils/mitigation.py

from fairlearn.reductions import ExponentiatedGradient, DemographicParity, EqualizedOdds
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder, LabelEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import SGDClassifier
import pandas as pd
import numpy as np

from .fairness_metrics import compute_fairness_metrics
from .fairness_metrics import compute_performance_metrics
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin
from sklearn.model_selection import train_test_split
import warnings
from sklearn.exceptions import ConvergenceWarning
from typing import Optional
# Suppress scikit-learn ConvergenceWarning messages that are expected
warnings.filterwarnings('ignore', category=ConvergenceWarning)


class PipelineSampleWeightAdapter(BaseEstimator, ClassifierMixin):
    """
    Wrapper to allow estimators which forward sample_weight to the final
    classifier step of a Pipeline. fairlearn's ExponentiatedGradient may
    pass `sample_weight` to the estimator's fit; sklearn's Pipeline does
    not accept `sample_weight` as a top-level kwarg — it must be passed
    to the final step using the `stepname__sample_weight` format. This
    small wrapper provides a fit signature that accepts sample_weight and
    forwards it correctly.
    """
    def __init__(self, pipeline, clf_step_name="clf"):
        self.pipeline = pipeline
        self.clf_step_name = clf_step_name

    def fit(self, X, y, sample_weight=None, **fit_params):
        kwargs = dict(fit_params)
        if sample_weight is not None:
            kwargs[f"{self.clf_step_name}__sample_weight"] = sample_weight
        self.pipeline.fit(X, y, **kwargs)
        return self

    def predict(self, X):
        return self.pipeline.predict(X)

    def predict_proba(self, X):
        return self.pipeline.predict_proba(X)

    def get_params(self, deep=True):
        out = {"pipeline": self.pipeline, "clf_step_name": self.clf_step_name}
        if deep and hasattr(self.pipeline, "get_params"):
            for k, v in self.pipeline.get_params(deep=True).items():
                out[f"pipeline__{k}"] = v
        return out

    def set_params(self, **params):
        if "pipeline" in params:
            self.pipeline = params.pop("pipeline")
        if "clf_step_name" in params:
            self.clf_step_name = params.pop("clf_step_name")
        pipeline_params = {k.replace("pipeline__", ""): v for k, v in params.items() if k.startswith("pipeline__")}
        if pipeline_params:
            self.pipeline.set_params(**pipeline_params)
        return self


class MitigatedBaselineWrapper(BaseEstimator, ClassifierMixin):
    """
    Wraps a Fairlearn ExponentiatedGradient mitigator into a predictable model
    that can be re-uploaded and used in analysis.
    """
    def __init__(self, mitigator, target_col: str, sensitive_col: str, metadata: Optional[dict] = None):
        self.mitigator = mitigator
        self.target_col = target_col
        self.sensitive_col = sensitive_col
        self.metadata = metadata or {}

    def predict(self, X):
        # X should be feature matrix without target/sensitive columns.
        return self.mitigator.predict(X)

    @staticmethod
    def from_saved_dict(d: dict):
        return MitigatedBaselineWrapper(
            mitigator=d.get("mitigator"),
            target_col=d.get("target_col"),
            sensitive_col=d.get("sensitive_col"),
            metadata={k: v for k, v in d.items() if k not in ("mitigator", "transformer", "label_encoder")}
        )


class MitigatedUserModelWrapper(BaseEstimator, ClassifierMixin):
    """
    Wraps a user model with stored preprocessing + group thresholds so it can
    be re-uploaded and used for fairness analysis.
    """
    def __init__(
        self,
        final_model,
        transformer,
        group_thresholds: dict,
        sensitive_col: str,
        target_col: Optional[str] = None,
        default_threshold: float = 0.5,
        constraint: str = "demographic_parity",
        metadata: Optional[dict] = None,
    ):
        self.final_model = final_model
        self.transformer = transformer
        self.group_thresholds = {str(k): float(v) for k, v in (group_thresholds or {}).items()}
        self.sensitive_col = sensitive_col
        self.target_col = target_col
        self.default_threshold = float(default_threshold)
        self.constraint = constraint
        self.metadata = metadata or {}

    def _scores(self, X_transformed):
        y_scores = None
        if hasattr(self.final_model, "predict_proba"):
            try:
                y_proba = self.final_model.predict_proba(X_transformed)
                if y_proba.ndim == 2 and y_proba.shape[1] >= 2:
                    y_scores = y_proba[:, 1]
                else:
                    y_scores = y_proba.flatten()
            except Exception:
                y_scores = None
        if y_scores is None:
            y_pred = self.final_model.predict(X_transformed)
            y_scores = np.asarray(y_pred, dtype=float).flatten()
        return y_scores

    def predict_with_sensitive(self, df: pd.DataFrame, target_col: Optional[str] = None, sensitive_col: Optional[str] = None):
        if not hasattr(df, "columns"):
            raise ValueError("predict_with_sensitive expects a pandas DataFrame with columns.")

        sens_col = sensitive_col or self.sensitive_col
        if not sens_col:
            raise ValueError("Sensitive column is required for mitigated user-model predictions.")
        if sens_col not in df.columns:
            raise ValueError(f"Sensitive column '{sens_col}' not found in input data.")

        X = df.copy()
        tcol = target_col or self.target_col
        if tcol and tcol in X.columns:
            X = X.drop(columns=[tcol], errors="ignore")
        sensitive = X[sens_col].values
        X = X.drop(columns=[sens_col], errors="ignore")

        X_t = self.transformer.transform(X)
        scores = self._scores(X_t)

        preds = np.zeros(len(scores), dtype=int)
        groups = np.unique(sensitive)
        for g in groups:
            mask = sensitive == g
            th = self.group_thresholds.get(str(g), self.default_threshold)
            preds[mask] = (scores[mask] >= th).astype(int)
        return preds

    def predict(self, X):
        # If DataFrame with sensitive column, use it directly.
        if hasattr(X, "columns") and self.sensitive_col in X.columns:
            return self.predict_with_sensitive(X, sensitive_col=self.sensitive_col, target_col=self.target_col)
        raise ValueError("Sensitive column required for mitigated user-model predictions. Use predict_with_sensitive(df).")

    @staticmethod
    def from_saved_dict(d: dict):
        return MitigatedUserModelWrapper(
            final_model=d.get("final_model"),
            transformer=d.get("transformer"),
            group_thresholds=d.get("group_thresholds") or {},
            sensitive_col=d.get("sensitive_col"),
            target_col=d.get("target_col"),
            default_threshold=d.get("default_threshold", 0.5),
            constraint=d.get("constraint", "demographic_parity"),
            metadata={k: v for k, v in d.items() if k not in ("final_model", "transformer", "group_thresholds")}
        )


def _prepare_features(df: pd.DataFrame, target_col: str, sensitive_col: str):
    """
    Prepares numerical + categorical preprocessing transformer.
    Sensitive attribute is excluded from X.
    """
    X = df.drop(columns=[target_col, sensitive_col], errors='ignore')

    numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = X.select_dtypes(exclude=[np.number]).columns.tolist()

    transformer = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=True), cat_cols),
        ],
        remainder="drop",
        sparse_threshold=0.0,
    )
    return transformer


def build_transformer(df: pd.DataFrame, target_col: str, sensitive_col: str):
    """
    Build a preprocessing transformer used by the baseline trainer and optional model-wrapping.
    Returns the ColumnTransformer and strategy/time estimate used.
    """
    X = df.drop(columns=[target_col], errors='ignore')
    X = X.drop(columns=[sensitive_col], errors='ignore')

    numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = X.select_dtypes(exclude=[np.number]).columns.tolist()

    est_ohe_dims = sum([int(df[c].nunique()) for c in cat_cols]) if cat_cols else 0
    rows = df.shape[0]
    use_fast_path = (rows > 20000) or (est_ohe_dims > 1000)

    if use_fast_path:
        n_features = 2 ** 12
        transformer = ColumnTransformer(
            transformers=[
                ("num", StandardScaler(), numeric_cols),
                ("cat", CatHasher(cat_cols, n_features=n_features), cat_cols),
            ],
            remainder="drop",
            sparse_threshold=0.0,
        )
        strategy = "fast-hash-sgd"
        time_estimate = max(5, int(rows / 1000 * 2))
    else:
        transformer = _prepare_features(df, target_col, sensitive_col)
        strategy = "ohe-logistic"
        time_estimate = max(10, int(rows / 1000 * 3))

    return transformer, strategy, time_estimate


def train_baseline_only(df: pd.DataFrame, target_col: str, sensitive_col: str):
    """
    Train only the baseline pipeline (preprocessor + classifier) and return baseline
    predictions and baseline fairness metrics. This is faster than running the full
    mitigation helper since it does not fit the ExponentiatedGradient mitigator.
    """
    le = LabelEncoder()
    y = le.fit_transform(df[target_col])

    transformer, strategy, time_estimate = build_transformer(df, target_col, sensitive_col)

    # choose classifier based on strategy
    if strategy == "fast-hash-sgd":
        base_clf = SGDClassifier(loss='log_loss', max_iter=1000, tol=1e-3, random_state=42)
    else:
        base_clf = LogisticRegression(max_iter=2000, solver='saga', n_jobs=-1, random_state=42)

    X = df.drop(columns=[target_col], errors='ignore')
    X = X.drop(columns=[sensitive_col], errors='ignore')
    y_raw = df[target_col]
    sens_raw = df[sensitive_col] if sensitive_col in df.columns else None

    # Holdout split for more honest metrics
    try:
        X_train, X_test, y_train, y_test, sens_train, sens_test = train_test_split(
            X, y, sens_raw, test_size=0.2, random_state=42, stratify=y
        )
    except Exception:
        # Fallback if stratify fails (e.g., tiny classes)
        X_train, X_test, y_train, y_test, sens_train, sens_test = train_test_split(
            X, y, sens_raw, test_size=0.2, random_state=42
        )

    clf_pipeline = Pipeline(steps=[
        ("pre", transformer),
        ("clf", base_clf)
    ])

    clf_pipeline.fit(X_train, y_train)
    y_pred_baseline = clf_pipeline.predict(X_train)

    tmp_baseline = pd.DataFrame(X_train).copy()
    tmp_baseline[target_col] = y_train
    if sens_train is not None:
        tmp_baseline[sensitive_col] = sens_train
    tmp_baseline["y_pred_baseline"] = y_pred_baseline

    metrics_baseline = compute_fairness_metrics(
        tmp_baseline,
        target_col=target_col,
        sensitive_col=sensitive_col,
        pred_col="y_pred_baseline"
    )
    performance_baseline = compute_performance_metrics(y_train, y_pred_baseline)
    # Test/holdout metrics
    metrics_baseline_test = None
    if X_test is not None and len(X_test) > 0:
        y_pred_test = clf_pipeline.predict(X_test)
        tmp_test = pd.DataFrame(X_test).copy()
        tmp_test[target_col] = y_test
        if sens_test is not None:
            tmp_test[sensitive_col] = sens_test
        tmp_test["y_pred_baseline"] = y_pred_test
        metrics_baseline_test = compute_fairness_metrics(
            tmp_test,
            target_col=target_col,
            sensitive_col=sensitive_col,
            pred_col="y_pred_baseline"
        )
        performance_baseline_test = compute_performance_metrics(y_test, y_pred_test)
    else:
        performance_baseline_test = None

    return {
        "predictions": y_pred_baseline.tolist(),
        "metrics_baseline": metrics_baseline,
        "metrics_baseline_test": metrics_baseline_test,
        "performance_baseline": performance_baseline,
        "performance_baseline_test": performance_baseline_test,
        "transformer": transformer,
        "label_encoder": le,
        "strategy": strategy,
        "time_estimate_seconds": time_estimate,
        "pipeline": clf_pipeline,
    }


class CatHasher(BaseEstimator, TransformerMixin):
    """scikit-learn compatible transformer that applies FeatureHasher to categorical columns.

    This implements `get_params` and `set_params` so it can be cloned/pickled by sklearn utilities.
    """
    def __init__(self, cols, n_features=2**12):
        self.cols = cols
        self.n_features = n_features
        # hasher will be (re)created in __init__ and when params change
        self.hasher = FeatureHasher(n_features=self.n_features, input_type='dict')

    def fit(self, X, y=None):
        # nothing to fit for hashing
        return self

    def transform(self, X):
        # X is expected to be a DataFrame or array-like with same columns
        # Convert each row's categorical columns to a dict
        if hasattr(X, 'loc'):
            df = X
            # dicts = df[self.cols].fillna('MISSING').astype(str).to_dict(orient='records')
            
            # Cast to object before fillna so pandas Categorical columns can
            # accept the placeholder value without category-mismatch errors.
            safe = df[self.cols].astype(object).fillna('MISSING').astype(str)
            dicts = safe.to_dict(orient='records')
        else:
            # X may be a 2D numpy array (subset of columns). Convert rows to dicts using self.cols
            arr = np.asarray(X)
            if arr.ndim == 1:
                arr = arr.reshape(-1, 1)
            dicts = []
            for row in arr:
                row_vals = [str(v) if (v is not None and not (isinstance(v, float) and np.isnan(v))) else 'MISSING' for v in row]
                dicts.append(dict(zip(self.cols, row_vals)))
        return self.hasher.transform(dicts)

    def get_params(self, deep=True):
        return {"cols": self.cols, "n_features": self.n_features}

    def set_params(self, **params):
        if "cols" in params:
            self.cols = params.pop("cols")
        if "n_features" in params:
            self.n_features = params.pop("n_features")
        # recreate hasher if params changed
        self.hasher = FeatureHasher(n_features=self.n_features, input_type='dict')
        return self


def mitigate_with_exponentiated_gradient(df: pd.DataFrame, target_col: str, sensitive_col: str,
                                         constraint="demographic_parity"):
    """
    Runs Fairlearn mitigation using ExponentiatedGradient with chosen constraint.
    - Ensures target is binary numeric (0/1)
    - Ensures sensitive attribute is not in the feature set
    - Computes fairness metrics after mitigation
    """

    # ===============================
    # 1. Encode target → 0/1
    # ===============================
    le = LabelEncoder()
    y = le.fit_transform(df[target_col])   # Yes/No → 1/0

    # Sensitive features remain as-is (string labels allowed)
    sensitive = df[sensitive_col].values

    # ===============================
    # 2. Prepare feature matrix X
    # ===============================
    X = df.drop(columns=[target_col])              # original X
    X = X.drop(columns=[sensitive_col])            # remove sensitive from X

    numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = X.select_dtypes(exclude=[np.number]).columns.tolist()

    # Estimate OHE dimensionality to decide on fast path
    est_ohe_dims = sum([int(df[c].nunique()) for c in cat_cols]) if cat_cols else 0
    rows = df.shape[0]

    # Heuristics: use fast hashed + SGD path for large datasets or very high-cardinality categoricals
    use_fast_path = (rows > 20000) or (est_ohe_dims > 1000)

    if use_fast_path:
        # Fast pipeline: scale numeric, hash categorical to fixed-size sparse features, use SGD
        n_features = 2 ** 12
        transformer = ColumnTransformer(
            transformers=[
                ("num", StandardScaler(), numeric_cols),
                ("cat", CatHasher(cat_cols, n_features=n_features), cat_cols),
            ],
            remainder="drop",
            sparse_threshold=0.0,
        )

        # use 'log_loss' name for logistic loss (newer sklearn versions)
        base_clf = SGDClassifier(loss='log_loss', max_iter=1000, tol=1e-3)
        strategy = "fast-hash-sgd"
        # rough time estimate (seconds): 2s per 1000 rows as conservative baseline
        time_estimate = max(5, int(rows / 1000 * 2))
    else:
        # Standard pipeline: OHE + LogisticRegression with saga
        transformer = _prepare_features(df, target_col, sensitive_col)
        base_clf = LogisticRegression(max_iter=2000, solver='saga', n_jobs=-1)
        strategy = "ohe-logistic"
        time_estimate = max(10, int(rows / 1000 * 3))

    clf_pipeline = Pipeline(steps=[
        ("pre", transformer),
        ("clf", base_clf)
    ])

    wrapped_estimator = PipelineSampleWeightAdapter(clf_pipeline, clf_step_name="clf")

    # Choose constraint
    cons = DemographicParity() if constraint == "demographic_parity" else EqualizedOdds()

    mitigator = ExponentiatedGradient(
        estimator=wrapped_estimator,
        constraints=cons
    )

    # ===============================
    # 4. Fit baseline pipeline for pre-mitigation metrics
    # ===============================
    # Holdout split for reporting
    try:
        X_train, X_test, y_train, y_test, sens_train, sens_test = train_test_split(
            X, y, sensitive, test_size=0.2, random_state=42, stratify=y
        )
    except Exception:
        X_train, X_test, y_train, y_test, sens_train, sens_test = train_test_split(
            X, y, sensitive, test_size=0.2, random_state=42
        )

    clf_pipeline.fit(X_train, y_train)
    y_pred_baseline = clf_pipeline.predict(X_train)

    # ===============================
    # 5. Fit mitigator
    # ===============================
    mitigator.fit(X_train, y_train, sensitive_features=sens_train)

    # Predict
    y_pred_mitigated = mitigator.predict(X_train)

    # ===============================
    # 6. Compute baseline (pre-mitigation) metrics
    # ===============================
    tmp_baseline = pd.DataFrame(X_train).copy()
    tmp_baseline[target_col] = y_train
    tmp_baseline[sensitive_col] = sens_train
    tmp_baseline["y_pred_baseline"] = y_pred_baseline

    metrics_baseline = compute_fairness_metrics(
        tmp_baseline,
        target_col=target_col,
        sensitive_col=sensitive_col,
        pred_col="y_pred_baseline"
    )

    # ===============================
    # 6. Build temp DF for mitigation metric evaluation
    # ===============================
    tmp = pd.DataFrame(X_train).copy()
    tmp[target_col] = y_train
    tmp[sensitive_col] = sens_train
    tmp["y_pred_mitigated"] = y_pred_mitigated

    # ===============================
    # 7. Compute mitigated metrics
    # ===============================
    metrics_after = compute_fairness_metrics(
        tmp,
        target_col=target_col,
        sensitive_col=sensitive_col,
        pred_col="y_pred_mitigated"
    )
    performance_baseline = compute_performance_metrics(y_train, y_pred_baseline)
    performance_after = compute_performance_metrics(y_train, y_pred_mitigated)
    # Holdout metrics
    metrics_baseline_test = None
    metrics_after_test = None
    if X_test is not None and len(X_test) > 0:
        y_pred_baseline_test = clf_pipeline.predict(X_test)
        y_pred_mitigated_test = mitigator.predict(X_test)
        tmp_b_test = pd.DataFrame(X_test).copy()
        tmp_b_test[target_col] = y_test
        tmp_b_test[sensitive_col] = sens_test
        tmp_b_test["y_pred_baseline"] = y_pred_baseline_test
        metrics_baseline_test = compute_fairness_metrics(
            tmp_b_test, target_col=target_col, sensitive_col=sensitive_col, pred_col="y_pred_baseline"
        )
        tmp_m_test = pd.DataFrame(X_test).copy()
        tmp_m_test[target_col] = y_test
        tmp_m_test[sensitive_col] = sens_test
        tmp_m_test["y_pred_mitigated"] = y_pred_mitigated_test
        metrics_after_test = compute_fairness_metrics(
            tmp_m_test, target_col=target_col, sensitive_col=sensitive_col, pred_col="y_pred_mitigated"
        )
        performance_baseline_test = compute_performance_metrics(y_test, y_pred_baseline_test)
        performance_after_test = compute_performance_metrics(y_test, y_pred_mitigated_test)
    else:
        performance_baseline_test = None
        performance_after_test = None

    return {
        "predictions": y_pred_mitigated.tolist(),
        "metrics_baseline": metrics_baseline,
        "metrics_after_mitigation": metrics_after,
        "metrics_baseline_test": metrics_baseline_test,
        "metrics_after_mitigation_test": metrics_after_test,
        "performance_baseline": performance_baseline,
        "performance_after_mitigation": performance_after,
        "performance_baseline_test": performance_baseline_test,
        "performance_after_mitigation_test": performance_after_test,
        "num_predictors": len(mitigator.predictors_),
        "weights": [float(w) for w in mitigator.weights_],
        "mitigator": mitigator,
        "transformer": transformer,
        "label_encoder": le,
        "strategy": strategy,
        "time_estimate_seconds": time_estimate,
        "predictions_mitigated_test": y_pred_mitigated_test.tolist() if X_test is not None and len(X_test) > 0 else None
    }


def mitigate_user_model(df: pd.DataFrame, user_model, target_col: str, sensitive_col: str,
                       constraint="demographic_parity"):
    """
    Applies fairness mitigation to a user-provided pre-trained model using POSTPROCESSING.
    
    Strategy:
    - If model is a Pipeline, extract ONLY the final classifier (skip preprocessing)
    - Apply OUR OWN standard preprocessing to match what the classifier expects
    - Get predictions from the classifier using our preprocessed features
    - Apply threshold adjustment per group for fairness
    
    This avoids feature name mismatch issues by using our own preprocessing.
    
    Args:
        df: DataFrame with data (must contain target_col and sensitive_col)
        user_model: Pre-trained classifier (Pipeline or raw model)
        target_col: Name of target column (ground truth labels)
        sensitive_col: Name of sensitive attribute column
        constraint: "demographic_parity" or "equalized_odds"
    
    Returns:
        Dict with baseline metrics, mitigated metrics
    """
    
    # ===============================
    # 1. Encode target → 0/1
    # ===============================
    le = LabelEncoder()
    y_true = le.fit_transform(df[target_col])
    
    # Sensitive features
    sensitive = df[sensitive_col].values
    
    # ===============================
    # 2. Prepare feature matrix X
    # ===============================
    X = df.drop(columns=[target_col, sensitive_col], errors='ignore')

    # Guard: mitigated user models are tied to a specific sensitive attribute
    if isinstance(user_model, MitigatedUserModelWrapper):
        if user_model.sensitive_col and user_model.sensitive_col != sensitive_col:
            raise ValueError(
                f"Uploaded mitigated model was created with sensitive column '{user_model.sensitive_col}'. "
                f"Please use the same sensitive column."
            )
    
    def _is_pipeline(m):
        return isinstance(m, Pipeline) or hasattr(m, "named_steps")

    # ===============================
    # 3. Extract final classifier from Pipeline if needed
    # ===============================
    final_model = user_model
    transformer_used = None

    # If already a mitigated wrapper, reuse its stored transformer when appropriate
    if isinstance(user_model, MitigatedUserModelWrapper):
        final_model = user_model.final_model
        transformer_used = user_model.transformer
    elif isinstance(user_model, Pipeline):
        # Model is a Pipeline - extract ONLY the final step (classifier)
        # We'll apply our own preprocessing to avoid feature mismatch
        steps = user_model.named_steps
        step_names = list(steps.keys())
        final_model = steps[step_names[-1]]  # Get the last step (classifier)

    # ===============================
    # 4. Preprocess features (only if final_model is not a Pipeline)
    # ===============================
    if _is_pipeline(final_model):
        X_transformed = X  # pipeline will handle preprocessing internally
    else:
        # If model expects already-encoded features, skip preprocessing
        fm_expected = getattr(final_model, "n_features_in_", None)
        if fm_expected is not None and X.shape[1] == fm_expected:
            X_transformed = X
            transformer_used = None
        else:
            if transformer_used is None:
                # Build a standard transformer (same as used in baseline training)
                transformer_used, _, _ = build_transformer(df, target_col, sensitive_col)
                transformer_used.fit(X)

            expected = None
            if hasattr(transformer_used, "n_features_in_"):
                expected = transformer_used.n_features_in_
            elif hasattr(transformer_used, "feature_names_in_"):
                expected = len(transformer_used.feature_names_in_)

            if expected is not None and X.shape[1] != expected:
                raise ValueError(
                    f"Input has {X.shape[1]} features, but preprocessing expects {expected}. "
                    f"Use the original (non-preprocessed) dataset or a model that matches these features."
                )
            X_transformed = transformer_used.transform(X)
    
    # ===============================
    # 5. Get baseline predictions and scores
    # ===============================
    y_scores = None
    y_pred_baseline = None
    
    # Try to get probabilities first
    try:
        if hasattr(final_model, 'predict_proba'):
            y_proba = final_model.predict_proba(X_transformed)
            if y_proba.ndim == 2 and y_proba.shape[1] >= 2:
                y_scores = y_proba[:, 1]  # Probability of class 1
            else:
                y_scores = y_proba.flatten()
    except Exception:
        pass
    
    # If no proba, try predictions as scores
    if y_scores is None:
        try:
            y_pred_baseline = final_model.predict(X_transformed)
            y_scores = np.asarray(y_pred_baseline, dtype=float)
        except Exception as e_pred:
            # If still fails, raise detailed error
            error_msg = f"Failed to get predictions from user model classifier. "
            error_msg += f"The model may require a different preprocessing approach. "
            error_msg += f"Error: {str(e_pred)}"
            raise ValueError(error_msg)
    
    # Threshold scores at 0.5 for baseline predictions
    y_pred_baseline = (y_scores >= 0.5).astype(int)
    
    # Ensure binary encoding
    y_pred_baseline = np.asarray(y_pred_baseline)
    if y_pred_baseline.dtype == object:
        le_baseline = LabelEncoder()
        y_pred_baseline = le_baseline.fit_transform(y_pred_baseline)
    else:
        y_pred_baseline = y_pred_baseline.astype(int)
    
    # ===============================
    # 4. Compute baseline metrics
    # ===============================
    tmp_baseline = df.copy()
    tmp_baseline["y_pred_baseline"] = y_pred_baseline
    
    metrics_baseline = compute_fairness_metrics(
        tmp_baseline,
        target_col=target_col,
        sensitive_col=sensitive_col,
        pred_col="y_pred_baseline"
    )
    
    # ===============================
    # 5. Apply postprocessing mitigation using threshold tuning
    # ===============================
    from sklearn.utils import column_or_1d
    sensitive_col_encoded = column_or_1d(sensitive)
    
    # Get unique groups
    groups = np.unique(sensitive_col_encoded)
    group_thresholds = {}
    
    # For each group, find threshold that improves fairness while maintaining reasonable accuracy
    y_pred_mitigated = y_pred_baseline.copy()
    
    if constraint == "demographic_parity":
        # Goal: equal selection rates across groups
        # Strategy: adjust thresholds to equalize positive prediction rates
        target_pos_rate = np.mean(y_pred_baseline)
        
        for group in groups:
            group_mask = (sensitive_col_encoded == group)
            group_scores = y_scores[group_mask]
            
            if len(group_scores) > 0:
                # Find threshold for this group that gives ~target_pos_rate
                sorted_scores = np.sort(group_scores)[::-1]
                target_count = max(1, int(len(group_scores) * target_pos_rate))
                threshold = sorted_scores[min(target_count - 1, len(sorted_scores) - 1)]
                group_thresholds[group] = threshold
                y_pred_mitigated[group_mask] = (group_scores >= threshold).astype(int)
    
    else:  # equalized_odds
        # Goal: equal TPR and FPR across groups
        # Strategy: find threshold that balances TPR/FPR for each group
        for group in groups:
            group_mask = (sensitive_col_encoded == group)
            group_scores = y_scores[group_mask]
            group_y_true = y_true[group_mask]
            
            if len(group_scores) > 0 and (np.sum(group_y_true) > 0 and np.sum(1 - group_y_true) > 0):
                # Find threshold that maximizes TPR while keeping FPR reasonable
                best_threshold = 0.5
                best_score = -np.inf
                
                for th in np.linspace(0, 1, 21):
                    group_pred = (group_scores >= th).astype(int)
                    tp = np.sum((group_pred == 1) & (group_y_true == 1))
                    fp = np.sum((group_pred == 1) & (group_y_true == 0))
                    fn = np.sum((group_pred == 0) & (group_y_true == 1))
                    tn = np.sum((group_pred == 0) & (group_y_true == 0))
                    
                    tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
                    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
                    
                    # Maximize TPR - |TPR - FPR| (balance TPR/FPR)
                    score = tpr - abs(tpr - fpr)
                    if score > best_score:
                        best_score = score
                        best_threshold = th
                
                group_thresholds[group] = best_threshold
                y_pred_mitigated[group_mask] = (group_scores >= best_threshold).astype(int)
            else:
                # If no positive or negative samples in group, use overall threshold
                group_thresholds[group] = 0.5
    
    # ===============================
    # 6. Compute mitigated metrics
    # ===============================
    tmp_mitigated = df.copy()
    tmp_mitigated["y_pred_mitigated"] = y_pred_mitigated
    
    metrics_after = compute_fairness_metrics(
        tmp_mitigated,
        target_col=target_col,
        sensitive_col=sensitive_col,
        pred_col="y_pred_mitigated"
    )
    performance_baseline = compute_performance_metrics(y_true, y_pred_baseline)
    performance_after = compute_performance_metrics(y_true, y_pred_mitigated)
    
    # Holdout metrics for user model
    metrics_baseline_test = None
    metrics_after_test = None
    if X is not None and len(X) > 1:
        try:
            X_train, X_test, y_train, y_test, sens_train, sens_test = train_test_split(
                X, y_true, sensitive, test_size=0.2, random_state=42, stratify=y_true
            )
        except Exception:
            X_train, X_test, y_train, y_test, sens_train, sens_test = train_test_split(
                X, y_true, sensitive, test_size=0.2, random_state=42
            )
        # Recompute predictions on holdout using same flow
        if _is_pipeline(final_model):
            y_scores_test = None
            if hasattr(final_model, "predict_proba"):
                try:
                    y_proba = final_model.predict_proba(X_test)
                    if y_proba.ndim == 2 and y_proba.shape[1] >= 2:
                        y_scores_test = y_proba[:, 1]
                    else:
                        y_scores_test = y_proba.flatten()
                except Exception:
                    y_scores_test = None
            if y_scores_test is None:
                y_scores_test = final_model.predict(X_test)
            y_pred_test = (np.asarray(y_scores_test, dtype=float) >= 0.5).astype(int)
        else:
            if transformer_used is not None:
                X_test_t = transformer_used.transform(X_test)
            else:
                X_test_t = X_test
            y_scores_test = None
            if hasattr(final_model, "predict_proba"):
                try:
                    y_proba = final_model.predict_proba(X_test_t)
                    if y_proba.ndim == 2 and y_proba.shape[1] >= 2:
                        y_scores_test = y_proba[:, 1]
                    else:
                        y_scores_test = y_proba.flatten()
                except Exception:
                    y_scores_test = None
            if y_scores_test is None:
                y_scores_test = final_model.predict(X_test_t)
            y_pred_test = (np.asarray(y_scores_test, dtype=float) >= 0.5).astype(int)

        tmp_b_test = pd.DataFrame(X_test).copy()
        tmp_b_test[target_col] = y_test
        tmp_b_test[sensitive_col] = sens_test
        tmp_b_test["y_pred_baseline"] = y_pred_test
        metrics_baseline_test = compute_fairness_metrics(
            tmp_b_test, target_col=target_col, sensitive_col=sensitive_col, pred_col="y_pred_baseline"
        )

        # Apply thresholds per group for mitigated test predictions
        preds_test = np.zeros(len(y_scores_test), dtype=int)
        groups_test = np.unique(sens_test)
        for g in groups_test:
            mask = sens_test == g
            th = group_thresholds.get(str(g), 0.5)
            preds_test[mask] = (np.asarray(y_scores_test, dtype=float)[mask] >= th).astype(int)

        tmp_m_test = pd.DataFrame(X_test).copy()
        tmp_m_test[target_col] = y_test
        tmp_m_test[sensitive_col] = sens_test
        tmp_m_test["y_pred_mitigated"] = preds_test
        metrics_after_test = compute_fairness_metrics(
            tmp_m_test, target_col=target_col, sensitive_col=sensitive_col, pred_col="y_pred_mitigated"
        )
        performance_baseline_test = compute_performance_metrics(y_test, y_pred_test)
        performance_after_test = compute_performance_metrics(y_test, preds_test)
    else:
        performance_baseline_test = None
        performance_after_test = None

    return {
        "predictions": y_pred_mitigated.tolist(),
        "metrics_baseline": metrics_baseline,
        "metrics_after_mitigation": metrics_after,
        "metrics_baseline_test": metrics_baseline_test,
        "metrics_after_mitigation_test": metrics_after_test,
        "performance_baseline": performance_baseline,
        "performance_after_mitigation": performance_after,
        "performance_baseline_test": performance_baseline_test,
        "performance_after_mitigation_test": performance_after_test,
        "mitigation_type": "postprocessing_threshold_tuning",
        "group_thresholds": {str(k): float(v) for k, v in group_thresholds.items()},
        "user_model": user_model,
        "final_model": final_model,
        "transformer": transformer_used
    }
