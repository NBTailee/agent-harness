import itertools
import math
import os
import re
import tempfile
import time
from dataclasses import dataclass
from typing import Any

WANDB_ENTITY = "leductai2201"
DEFAULT_PROJECT = "agent-harness-kaggle"
PROJECT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
RESERVED_PROJECTS = {"runs", "sweeps"}
STOP_TAG = "agent-stop"
STEP_KEY = "train/global_step"
# Used only when a run has no primary_metric in its config.
METRIC_KEYS = ("eval/accuracy", "eval/acc", "eval/f1", "eval/auc", "eval/r2",
               "eval/rmse", "eval/mae", "eval/matthews_correlation",
               "eval/pearson", "eval/rouge1", "eval/bleu", "eval/loss")
# AgentRun bookkeeping keys, not hyperparameters.
SKIP_CONFIG = {"framework", "fit_mode", "total_steps", "primary_metric", "goal",
               "kaggle_kernel"}


@dataclass
class FitThresholds:
    patience: int = 2                  # evals since the best eval loss
    min_delta: float = 0.02            # a 2% rise counts as worse (1% is noise)
    diverge_ratio: float = 1.5         # train loss at 1.5x its start
    plateau_drop: float = 0.10         # train loss dropped less than 10%
    underfit_after: float = 0.30       # judge underfit only after 30% progress
    late_progress: float = 0.80        # past this, let the run finish
    overfit_gap: float = 0.10          # single fit: train - eval score
    chance_level: float | None = None  # e.g. 0.5 for balanced binary


OVERFIT_EDITS = [
    "fewer epochs / rounds (stop near best_eval_step)",
    "stronger regularization: weight_decay, dropout, alpha/C, max_depth, "
    "min_child_weight, min_samples_leaf",
    "lower learning_rate",
    "more data / augmentation",
    "smaller model",
]
UNDERFIT_EDITS = [
    "raise learning_rate 2-3x",
    "more epochs / rounds",
    "weaker regularization",
    "bigger model / deeper trees",
    "check labels, features, tokenization, frozen layers",
]
DIVERGE_EDITS = [
    "lower learning_rate 3-10x",
    "gradient clipping (max_grad_norm=1.0)",
    "warmup",
    "fp16 only on T4 (no bf16)",
    "check labels and loss",
]


def _verdict(verdict, action, reason, edits, evidence):
    return {"verdict": verdict, "action": action, "reason": reason,
            "suggested_edits": edits, "evidence": evidence}


def _near(series, step, k=3):
    """Mean of the k points closest to step; single points are too noisy."""
    nearest = sorted(series, key=lambda p: abs(p[0] - step))[:k]
    return sum(v for _, v in nearest) / len(nearest)


def diagnose_fit(train, evals, metric=None, progress=None,
                 th: FitThresholds = FitThresholds()) -> dict:
    """Verdict for a run with curves. Inputs are (step, value) lists."""
    metric = metric or []
    ev: dict[str, Any] = {"train_points": len(train),
                          "eval_points": len(evals), "progress": progress}

    if any(math.isnan(v) or math.isinf(v) for _, v in train + evals):
        return _verdict("diverged", "stop_and_edit", "NaN/inf loss",
                        DIVERGE_EDITS, ev)

    if len(train) >= 5:
        first = sum(v for _, v in train[:3]) / 3
        last = sum(v for _, v in train[-3:]) / 3
        ev.update(train_loss_start=round(first, 4),
                  train_loss_now=round(last, 4))
        if last > first * th.diverge_ratio:
            return _verdict("diverged", "stop_and_edit",
                            f"train loss rose {first:.3f} -> {last:.3f}",
                            DIVERGE_EDITS, ev)

    if len(evals) >= th.patience + 1:
        losses = [v for _, v in evals]
        best_i = losses.index(min(losses))
        best_step, best = evals[best_i]
        ev.update(best_eval_loss=round(best, 4), best_eval_step=best_step,
                  eval_loss_now=round(losses[-1], 4))
        if train:
            ev["generalization_gap"] = round(losses[-1] - train[-1][1], 4)
        evals_since_best = len(losses) - 1 - best_i
        train_falling = bool(train) and _near(train, train[-1][0]) < _near(train, best_step)
        if (evals_since_best >= th.patience
                and losses[-1] > best * (1 + th.min_delta)
                and train_falling):
            late = progress is not None and progress >= th.late_progress
            return _verdict(
                "overfit", "let_finish" if late else "stop_and_edit",
                f"eval loss up for {evals_since_best} evals since step "
                f"{best_step} while train loss keeps falling",
                OVERFIT_EDITS, ev)

    if (progress is not None and progress >= th.underfit_after
            and len(train) >= 5):
        drop = 1 - ev["train_loss_now"] / max(ev["train_loss_start"], 1e-9)
        ev["train_loss_drop"] = round(drop, 3)
        near_chance = (th.chance_level is not None and metric
                       and metric[-1][1] < th.chance_level + 0.05)
        if drop < th.plateau_drop or near_chance:
            reason = ("train loss barely moved" if drop < th.plateau_drop
                      else "metric near chance level")
            return _verdict("underfit", "stop_and_edit", reason,
                            UNDERFIT_EDITS, ev)

    if len(evals) < 2:
        return _verdict("warming_up", "continue",
                        "not enough eval points yet", [], ev)
    return _verdict("healthy", "continue", "eval loss still near its best",
                    [], ev)


def diagnose_single(train_score, eval_score, goal="max",
                    th: FitThresholds = FitThresholds()) -> dict:
    """Verdict for a one-shot fit: final train vs eval score."""
    ev = {"train_score": train_score, "eval_score": eval_score}
    if train_score is None or eval_score is None:
        return _verdict("unknown", "final_only",
                        "log_final needs train and eval scores of the "
                        "primary metric", [], ev)
    if goal == "max":
        gap = train_score - eval_score
        low = (th.chance_level is not None
               and train_score < th.chance_level + 0.10)
    else:
        # Error metrics: relative gap.
        gap = (eval_score - train_score) / max(abs(train_score), 1e-9)
        low = False
    ev["gap"] = round(gap, 4)
    if gap > th.overfit_gap:
        return _verdict("overfit", "final_only",
                        f"train beats eval by {gap:.3f}", OVERFIT_EDITS, ev)
    if low:
        return _verdict("underfit", "final_only",
                        "train score near chance level", UNDERFIT_EDITS, ev)
    return _verdict("healthy", "final_only", "small train/eval gap", [], ev)


def wandb_enabled() -> bool:
    """On when WANDB_API_KEY is set, unless WANDB_ENABLED=0."""
    flag = os.environ.get("WANDB_ENABLED", "").strip()
    if flag == "0":
        return False
    return flag == "1" or bool(os.environ.get("WANDB_API_KEY"))


def validate_project(name: str) -> str:
    if not name or not PROJECT_RE.match(name):
        raise ValueError(
            f"Invalid W&B project name {name!r}: use letters, digits, '-', "
            "'_' or '.' (max 128).")
    if name.lower() in RESERVED_PROJECTS:
        # wandb.Api reads "entity/runs/<id>" as a URL path and drops the project.
        raise ValueError(f"W&B project name {name!r} is reserved; pick another.")
    return name


class WandbMonitor:
    """W&B access for the host tools. Entity is fixed; the project can change."""

    def __init__(self, project: str | None = None):
        self.entity = WANDB_ENTITY
        self.project = validate_project(
            project or os.environ.get("WANDB_KAGGLE_PROJECT", DEFAULT_PROJECT))
        self._api = None

    @property
    def api(self):
        if self._api is None:
            import wandb  # imported lazily so the harness runs without it
            key = os.environ.get("WANDB_API_KEY")
            if not key:
                raise ValueError("WANDB_API_KEY is not set in the environment.")
            self._api = wandb.Api(api_key=key, timeout=30)
        return self._api

    @property
    def path(self) -> str:
        return f"{self.entity}/{self.project}"

    def list_projects(self) -> list[dict]:
        self.api.flush()
        return [{"name": p.name, "url": p.url,
                 "active": p.name == self.project}
                for p in self.api.projects(self.entity)]

    def project_exists(self, name: str) -> bool:
        return any(p["name"] == name for p in self.list_projects())

    def create_project(self, name: str) -> None:
        self.api.create_project(validate_project(name), self.entity)

    def ensure_project(self, name: str) -> bool:
        """Create the project if missing and make it active. True if created."""
        created = not self.project_exists(validate_project(name))
        if created:
            self.create_project(name)
        self.project = name
        return created

    def list_runs(self, project: str | None = None, group: str | None = None,
                  state: str | None = None, limit: int = 20) -> list[dict]:
        self.api.flush()
        filters = {}
        if group:
            filters["group"] = group
        if state:
            filters["state"] = state
        path = f"{self.entity}/{validate_project(project or self.project)}"
        rows = []
        for run in itertools.islice(
                self.api.runs(path, filters=filters, order="-created_at"),
                limit):
            key, _ = self.primary(run)
            rows.append({
                "id": run.id,
                "name": run.name,
                "state": run.state,
                "group": run.group,
                "created_at": run.created_at,
                "framework": run.config.get("framework"),
                "primary_metric": key,
                "value": run.summary.get(f"best/{key}",
                                         run.summary.get(key)) if key else None,
                "tags": list(run.tags),
                "source": "host" if "host" in run.tags else "kaggle",
                "url": run.url,
            })
        return rows

    def create_run(self, name: str, project: str | None = None,
                   config: dict | None = None, metrics: dict | None = None,
                   group: str | None = None, tags: list | None = None,
                   notes: str | None = None) -> dict:
        """Create a finished run from the host, e.g. a baseline or a note."""
        import wandb
        if not os.environ.get("WANDB_API_KEY"):
            raise ValueError("WANDB_API_KEY is not set in the environment.")
        metrics = metrics or {}
        config = dict(config or {})
        # Lets list/compare tools find the metric of host runs too.
        key = next((k for k in METRIC_KEYS if k in metrics), None)
        if key and "primary_metric" not in config:
            config["primary_metric"] = key
            config["goal"] = "min" if key.endswith(("loss", "rmse", "mae", "error")) else "max"
        run = wandb.init(
            entity=self.entity,
            project=validate_project(project or self.project),
            name=name, group=group, notes=notes,
            tags=sorted(set(tags or []) | {"host"}),  # not a kernel run
            config=config, job_type="agent",
            dir=tempfile.gettempdir(),  # keep wandb/ out of the repo
            reinit="create_new",
            settings=wandb.Settings(silent=True),
        )
        try:
            if metrics:
                run.log(metrics)
                run.summary.update(metrics)
            info = {"id": run.id, "name": run.name, "url": run.url,
                    "project": run.project}
        finally:
            run.finish()
        if metrics:
            # Set the summary once more after the SDK's own final upload, which
            # could otherwise overwrite it. No read-back: the API lags a minute.
            time.sleep(3)
            try:
                self.api.flush()
                self.api.run(f"{self.entity}/{info['project']}/{info['id']}").summary.update(metrics)
            except Exception:
                pass  # the SDK summary above usually lands anyway
        info["note"] = ("W&B can take a minute before a new run shows in "
                        "wandb_list_runs / wandb_compare_runs. Do not create it again.")
        return info

    def latest_run(self, group: str):
        self.api.flush()  # Api caches results; we want fresh data
        runs = self.api.runs(self.path, filters={"group": group},
                             order="-created_at", per_page=1)
        return next(iter(runs), None)

    @staticmethod
    def series(run, key: str, samples: int = 500) -> list[tuple[int, float]]:
        # history() drops rows missing any key, so fetch one key at a time.
        rows = run.history(keys=[key, STEP_KEY], samples=samples,
                           pandas=False)
        return sorted((int(r[STEP_KEY]), float(r[key])) for r in rows
                      if r.get(key) is not None
                      and r.get(STEP_KEY) is not None)

    @staticmethod
    def primary(run) -> tuple[str | None, str]:
        """(metric key, goal) from the run config, else a guess."""
        key = run.config.get("primary_metric")
        if not key:
            key = next((k for k in METRIC_KEYS if k in run.summary), None)
        goal = run.config.get("goal") or (
            "min" if key and key.endswith(("loss", "rmse", "mae")) else "max")
        return key, goal

    def request_stop(self, run, reason: str) -> None:
        if STOP_TAG not in run.tags:
            run.tags.append(STOP_TAG)
        run.notes = f"{run.notes or ''}\n[agent-stop] {reason}".strip()
        run.update()

    def leaderboard(self, metric: str | None, goal: str | None,
                    top_k: int = 5, group: str | None = None):
        filters = {"group": group} if group else {}  # project scope: every run
        runs = list(itertools.islice(
            self.api.runs(self.path, filters=filters, order="-created_at"),
            200))
        if runs and not metric:
            # Host runs may lack a primary metric; prefer a run that has one.
            source = next((r for r in runs if r.config.get("primary_metric")), runs[0])
            metric, guessed = self.primary(source)
            goal = goal or guessed
            if not metric:
                raise ValueError("No primary metric found in these runs; pass "
                                 "metric=, e.g. 'eval/accuracy' or 'eval/loss'.")
        if not goal and metric:
            goal = "min" if metric.endswith(("loss", "rmse", "mae", "error")) else "max"
        goal = goal or "max"

        def score(run):
            # Best value if AgentRun tracked it, else the last one.
            value = run.summary.get(f"best/{metric}", run.summary.get(metric))
            if isinstance(value, (int, float)) and not math.isnan(value):
                return value
            return None

        scored = [(score(r), r) for r in runs]
        scored = [(s, r) for s, r in scored if s is not None]
        scored.sort(key=lambda x: x[0], reverse=(goal == "max"))

        rows = []
        for i, (value, run) in enumerate(scored[:top_k]):
            hparams = {k: v for k, v in run.config.items()
                       if k not in SKIP_CONFIG and not k.startswith("_")
                       and isinstance(v, (int, float, str, bool))}
            rows.append({
                "rank": i + 1,
                "name": run.name,
                "state": run.state,
                "framework": run.config.get("framework"),
                metric: round(value, 4),  # best value if tracked
                "final": run.summary.get(metric),
                "best_step": run.summary.get("best/step"),
                "stop_reason": run.summary.get("stop_reason"),
                "hyperparameters": hparams,
                "kernel": run.config.get("kaggle_kernel"),
                "source": "host" if "host" in run.tags else "kaggle",
                "url": run.url,
            })
        return metric, goal, rows
