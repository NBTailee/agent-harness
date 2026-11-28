# ---- AgentRun (agent-harness) ----
# Do not copy or edit. train.py does `from agent_run import AgentRun`;
# kaggle_push puts this file in place of that line and fills in the two names below.
import math
import os
import time

KERNEL_SLUG = "INSERT_KERNEL_SLUG_HERE"  # filled by kaggle_push from kernel-metadata.json
WANDB_PROJECT = "INSERT_WANDB_PROJECT_HERE"  # filled by kaggle_push (active W&B project)
os.environ["WANDB_ENTITY"] = "leductai2201"
os.environ["WANDB_PROJECT"] = WANDB_PROJECT
os.environ["WANDB_DIR"] = "/kaggle/working"


def _load_keys():
    """Read keys/.env from the private dataset nbtailee22/secret-keys (dataset_sources)."""
    import glob
    paths = ["/kaggle/input/secret-keys/keys/.env"] + glob.glob(
        "/kaggle/input/**/secret-keys/keys/.env", recursive=True)
    for path in paths:
        if os.path.isfile(path):
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
            return True
    return False


if _load_keys() and os.environ.get("WANDB_API_KEY"):
    os.environ["WANDB_MODE"] = "online"
else:
    print("WANDB_OFFLINE: no WANDB_API_KEY in /kaggle/input/secret-keys/keys/.env "
          "(attach dataset nbtailee22/secret-keys); metrics saved offline only")
    os.environ["WANDB_MODE"] = "offline"
import wandb


class AgentRun:
    """Logs to W&B under the names the harness tools read; stops on the agent's tag or the local guard."""

    STOP_TAG = "agent-stop"

    def __init__(self, hparams: dict, framework: str, primary_metric="eval/loss",
                 goal="min", total_steps=None, fit_mode="curve", poll_seconds=30,
                 guard=True, guard_patience=3):
        self.online = os.environ["WANDB_MODE"] == "online"
        # Local guard: stops a bad run even when W&B (and the agent's stop) is unreachable.
        self.guard = guard and fit_mode == "curve"
        self.guard_patience = guard_patience
        self._train_losses, self._eval_losses = [], []  # (step, value)
        self.primary_metric, self.goal = primary_metric, goal
        self.poll_seconds, self._last_poll, self._api = poll_seconds, 0.0, None
        self.best, self.stopped, self._poll_failed = None, False, False
        self.total_steps, self._t0, self._last_print = total_steps, time.time(), 0.0
        self.run = wandb.init(
            group=KERNEL_SLUG,
            name=f"{KERNEL_SLUG}-{time.strftime('%m%d-%H%M%S')}",
            tags=["kaggle", KERNEL_SLUG, framework],
            config={**hparams, "framework": framework, "fit_mode": fit_mode,
                    "total_steps": total_steps, "primary_metric": primary_metric,
                    "goal": goal, "kaggle_kernel": KERNEL_SLUG},
        )
        self.run.define_metric("train/global_step")
        self.run.define_metric("*", step_metric="train/global_step")

    def set_total_steps(self, n):
        self.total_steps = int(n)
        self.run.config.update({"total_steps": int(n)}, allow_val_change=True)

    def log(self, step, train_loss=None, eval_loss=None, train=None, **eval_metrics):
        """Log one point. Returns True when it is the best so far on primary_metric."""
        data = {}
        if train_loss is not None:
            data["train/loss"] = float(train_loss)
        if eval_loss is not None:
            data["eval/loss"] = float(eval_loss)
        data.update({f"train/{k}": float(v) for k, v in (train or {}).items()})
        data.update({f"eval/{k}": float(v) for k, v in eval_metrics.items()
                     if v is not None})
        if not data:
            return False
        data["train/global_step"] = int(step)
        self.run.log(data)
        self._print_progress(int(step))
        best = self._update_best(data)
        if self.guard and not self.stopped:
            self._check_guard(int(step), data.get("train/loss"), data.get("eval/loss"))
        return best

    def _check_guard(self, step, train_loss, eval_loss):
        if train_loss is not None:
            self._train_losses.append((step, train_loss))
        if eval_loss is not None:
            self._eval_losses.append((step, eval_loss))
        if any(not math.isfinite(v) for v in (train_loss, eval_loss) if v is not None):
            return self._guard_stop(f"diverged: non-finite loss at step {step}")

        train = [v for _, v in self._train_losses]
        if len(train) >= 6 and sum(train[-3:]) > 1.5 * sum(train[:3]):
            return self._guard_stop(
                f"diverged: train loss rose {sum(train[:3]) / 3:.4f} -> {sum(train[-3:]) / 3:.4f}")

        # Overfit: eval loss up for `guard_patience` evals while train loss keeps falling.
        # Late in the run, let it finish: the best checkpoint is already saved.
        late = self.total_steps and step >= 0.8 * self.total_steps
        evals = self._eval_losses
        if late or len(evals) <= self.guard_patience or not self._train_losses:
            return
        best_i = min(range(len(evals)), key=lambda i: evals[i][1])
        best_step, best = evals[best_i]

        def train_near(s):  # mean of the 3 closest train losses; single points are noisy
            near = sorted(self._train_losses, key=lambda p: abs(p[0] - s))[:3]
            return sum(v for _, v in near) / len(near)

        if (len(evals) - 1 - best_i >= self.guard_patience
                and evals[-1][1] > best * 1.02
                and train_near(self._train_losses[-1][0]) < train_near(best_step)):
            self._guard_stop(
                f"overfit: eval loss up for {len(evals) - 1 - best_i} evals since "
                f"step {best_step} ({best:.4f} -> {evals[-1][1]:.4f})")

    def _guard_stop(self, reason):
        self.stopped = True
        self.run.summary["stop_reason"] = f"guard: {reason}"
        print(f"STOPPED_BY_GUARD: {reason}", flush=True)

    def _print_progress(self, step):
        # Plain line for kaggle_training_progress; tqdm frames only reach the log at the end.
        if time.time() - self._last_print < 10:
            return
        self._last_print = time.time()
        total = f"/{self.total_steps}" if self.total_steps else ""
        print(f"PROGRESS step={step}{total} elapsed={time.time() - self._t0:.1f}s",
              flush=True)

    def _update_best(self, data):
        value = data.get(self.primary_metric)
        if value is None or math.isnan(value):
            return False
        if self.best is None or (value > self.best if self.goal == "max"
                                 else value < self.best):
            self.best = value
            self.run.summary[f"best/{self.primary_metric}"] = value
            self.run.summary["best/step"] = data["train/global_step"]
            return True
        return False

    def should_stop(self):
        """Safe to call every step; asks W&B at most every poll_seconds."""
        if self.stopped:
            return True
        if not self.online or time.time() - self._last_poll < self.poll_seconds:
            return False
        self._last_poll = time.time()
        try:
            self._api = self._api or wandb.Api(timeout=15)
            self._api.flush()  # Api caches runs; without this the tags never change
            entity, project = self.run.entity, self.run.project
            tags = self._api.run(f"{entity}/{project}/{self.run.id}").tags
        except Exception as exc:
            if not self._poll_failed:  # a failed poll must not kill training
                print(f"STOP_POLL failed: {type(exc).__name__}: {exc}")
                self._poll_failed = True
            return False
        if self.STOP_TAG in tags:
            self.stopped = True
            self.run.summary["stop_reason"] = "agent"
            print("STOPPED_BY_AGENT")
        return self.stopped

    def log_final(self, train: dict, eval: dict):
        """For fit_mode='single': final scores, no curve."""
        self.run.summary.update({f"train/{k}": float(v) for k, v in train.items()})
        self.run.summary.update({f"eval/{k}": float(v) for k, v in eval.items()})
        print({"train": train, "eval": eval})

    def finish(self, **final_eval):
        """Numbers go to eval/<name>; anything else (e.g. stopped_by="guard") is kept as text."""
        for key, value in final_eval.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.run.summary[f"eval/{key}"] = float(value)
            else:
                self.run.summary[key] = str(value)
        if final_eval:
            print({"final_eval": final_eval})
        wandb.finish()
# ---- end AgentRun ----
