# pyright: reportUndefinedVariable=false, reportMissingImports=false
# AgentRun adapters. Copy only the section for your framework into train.py,
# below `from agent_run import AgentRun`.
# Do not also enable the framework's own W&B logger (HF report_to="wandb",
# Lightning WandbLogger, wandb.xgboost): it would log everything twice.


# ===== Plain PyTorch loop =====
# Step = optimizer step here. To count epochs instead, use total_steps=EPOCHS
# and call run.log / run.should_stop once per epoch.
run = AgentRun({"lr": LR, "batch_size": BS, "epochs": EPOCHS, "model": MODEL_NAME},
               framework="pytorch", primary_metric="eval/accuracy", goal="max",
               total_steps=EPOCHS * len(train_loader))
step = 0
for epoch in range(EPOCHS):
    model.train()
    for xb, yb in tqdm(train_loader):
        loss = criterion(model(xb.cuda()), yb.cuda())
        opt.zero_grad()
        loss.backward()
        opt.step()
        step += 1
        if step % 20 == 0:
            run.log(step, train_loss=loss.item())
        if step % EVAL_EVERY == 0:
            val_loss, val_acc = evaluate(model, val_loader)
            if run.log(step, eval_loss=val_loss, accuracy=val_acc):
                torch.save(model.state_dict(), "/kaggle/working/best.pt")
        if run.should_stop():
            break
    if run.stopped:
        break
run.finish(accuracy=evaluate(model, val_loader)[1])


# ===== PyTorch Lightning =====
import lightning as L


class AgentRunLightning(L.Callback):
    def __init__(self, run, every_n_steps=20):
        self.run, self.every = run, every_n_steps

    def on_train_start(self, trainer, pl_module):
        self.run.set_total_steps(trainer.estimated_stepping_batches)

    def on_train_batch_end(self, trainer, pl_module, outputs, batch, batch_idx):
        if trainer.global_step % self.every == 0:
            loss = outputs["loss"] if isinstance(outputs, dict) else outputs
            self.run.log(trainer.global_step, train_loss=float(loss))
        if self.run.should_stop():
            trainer.should_stop = True

    def on_validation_end(self, trainer, pl_module):
        if trainer.sanity_checking:
            return
        # The module must self.log("val_loss", ...) and other val_* metrics.
        m = {k[4:]: float(v) for k, v in trainer.callback_metrics.items()
             if k.startswith("val_")}
        self.run.log(trainer.global_step, eval_loss=m.pop("loss", None), **m)


run = AgentRun(HPARAMS, framework="lightning", primary_metric="eval/acc", goal="max")
trainer = L.Trainer(
    max_epochs=EPOCHS, logger=False, val_check_interval=0.25,
    callbacks=[AgentRunLightning(run),
               L.pytorch.callbacks.ModelCheckpoint(monitor="val_loss",
                                                   dirpath="/kaggle/working")])
trainer.fit(model, train_loader, val_loader)
run.finish()


# ===== Hugging Face Trainer =====
from transformers import TrainerCallback, EarlyStoppingCallback


class AgentRunHF(TrainerCallback):
    SKIP = ("runtime", "per_second", "epoch")

    def __init__(self, run):
        self.run = run

    def on_train_begin(self, args, state, control, **kwargs):
        self.run.set_total_steps(state.max_steps)

    def on_log(self, args, state, control, logs=None, **kwargs):
        logs = logs or {}
        evals = {k[5:]: v for k, v in logs.items()
                 if k.startswith("eval_") and k != "eval_loss"
                 and isinstance(v, (int, float)) and not k.endswith(self.SKIP)}
        self.run.log(state.global_step, train_loss=logs.get("loss"),
                     eval_loss=logs.get("eval_loss"), **evals)

    def on_step_end(self, args, state, control, **kwargs):
        if self.run.should_stop():
            control.should_training_stop = True


run = AgentRun({"model_name": MODEL_NAME, "lr": LR, "epochs": EPOCHS},
               framework="huggingface", primary_metric="eval/accuracy", goal="max")
args = TrainingArguments(
    output_dir="/kaggle/working/out",
    report_to="none",  # AgentRun does the logging
    eval_strategy="steps", eval_steps=EVAL_STEPS,
    save_strategy="steps", save_steps=EVAL_STEPS,
    load_best_model_at_end=True, metric_for_best_model="eval_loss",
    greater_is_better=False, save_total_limit=2,
    logging_steps=20, fp16=True, disable_tqdm=False,
)
trainer = Trainer(model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds,
                  processing_class=tokenizer, compute_metrics=compute_metrics,
                  callbacks=[AgentRunHF(run), EarlyStoppingCallback(3)])
trainer.train()
run.finish(**{k[5:]: v for k, v in trainer.evaluate().items()
              if k.startswith("eval_") and isinstance(v, float)})


# ===== XGBoost =====
import xgboost as xgb


class AgentRunXGB(xgb.callback.TrainingCallback):
    def __init__(self, run, metric="logloss"):
        self.run, self.metric = run, metric

    def after_iteration(self, model, epoch, evals_log):
        self.run.log(epoch + 1,
                     train_loss=evals_log["train"][self.metric][-1],
                     eval_loss=evals_log["eval"][self.metric][-1])
        return self.run.should_stop()  # True ends boosting


run = AgentRun(PARAMS, framework="xgboost", total_steps=NUM_ROUNDS)
booster = xgb.train(PARAMS | {"eval_metric": "logloss", "device": "cuda"},
                    dtrain, num_boost_round=NUM_ROUNDS,
                    evals=[(dtrain, "train"), (dval, "eval")],
                    early_stopping_rounds=50, verbose_eval=50,
                    callbacks=[AgentRunXGB(run)])
run.finish(accuracy=accuracy_score(y_val, booster.predict(dval) > 0.5),
           best_iteration=booster.best_iteration)


# ===== LightGBM =====
import lightgbm as lgb


def agent_run_lgb(run):
    def callback(env):
        # Entries are (data_name, metric_name, value, higher_is_better).
        res = {r[0]: r[2] for r in env.evaluation_result_list}
        run.log(env.iteration + 1, train_loss=res.get("train"),
                eval_loss=res.get("valid"))
        if run.should_stop():
            raise lgb.callback.EarlyStopException(env.iteration,
                                                  env.evaluation_result_list)
    return callback


run = AgentRun(PARAMS, framework="lightgbm", total_steps=NUM_ROUNDS)
model = lgb.train(PARAMS | {"metric": "binary_logloss"}, dtrain,
                  num_boost_round=NUM_ROUNDS,
                  valid_sets=[dtrain, dval], valid_names=["train", "valid"],
                  callbacks=[agent_run_lgb(run), lgb.early_stopping(50),
                             lgb.log_evaluation(50)])
run.finish()


# ===== sklearn, iterative (partial_fit / warm_start) =====
import joblib
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, log_loss

run = AgentRun({"alpha": 1e-4, "loss": "log_loss", "epochs": EPOCHS},
               framework="sklearn", primary_metric="eval/accuracy", goal="max",
               total_steps=EPOCHS)
clf = SGDClassifier(loss="log_loss", alpha=1e-4)
for epoch in range(1, EPOCHS + 1):
    clf.partial_fit(X_tr, y_tr, classes=CLASSES)
    if run.log(epoch,
               train_loss=log_loss(y_tr, clf.predict_proba(X_tr)),
               eval_loss=log_loss(y_va, clf.predict_proba(X_va)),
               accuracy=accuracy_score(y_va, clf.predict(X_va))):
        joblib.dump(clf, "/kaggle/working/best.joblib")
    if run.should_stop():
        break
run.finish()
# Same loop works with warm_start=True (MLPClassifier) or a growing n_estimators.


# ===== sklearn, single fit (no curve, cannot be stopped) =====
from sklearn.metrics import f1_score
from sklearn.svm import SVC

run = AgentRun({"C": 1.0, "kernel": "rbf"}, framework="sklearn",
               primary_metric="eval/accuracy", goal="max", fit_mode="single")
model = SVC(C=1.0, kernel="rbf").fit(X_tr, y_tr)
run.log_final(train={"accuracy": model.score(X_tr, y_tr)},
              eval={"accuracy": model.score(X_va, y_va),
                    "f1": f1_score(y_va, model.predict(X_va), average="macro")})
run.finish()
# GridSearchCV: run.run.config.update(search.best_params_), then log_final
# with the best estimator's train and eval scores.
