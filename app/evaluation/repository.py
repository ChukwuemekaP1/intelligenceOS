"""In-memory and persistent evaluation run repository."""

from app.evaluation.models import EvaluationDataset, EvaluationRun, ExperimentComparison


class EvaluationRepository:
    """Stores evaluation datasets, completed evaluation runs,
    and facilitates experiment comparison.
    """

    def __init__(self) -> None:
        self._datasets: dict[str, EvaluationDataset] = {}
        self._runs: dict[str, EvaluationRun] = {}

    def save_dataset(self, dataset: EvaluationDataset) -> None:
        self._datasets[dataset.id] = dataset

    def get_dataset(self, dataset_id: str) -> EvaluationDataset | None:
        return self._datasets.get(dataset_id)

    def list_datasets(self, workspace_id: str | None = None) -> list[EvaluationDataset]:
        res = list(self._datasets.values())
        if workspace_id:
            res = [d for d in res if d.workspace_id == str(workspace_id)]
        return res

    def save_run(self, run: EvaluationRun) -> None:
        self._runs[run.run_id] = run

    def get_run(self, run_id: str) -> EvaluationRun | None:
        return self._runs.get(run_id)

    def list_runs(
        self, workspace_id: str | None = None, dataset_id: str | None = None
    ) -> list[EvaluationRun]:
        res = list(self._runs.values())
        if workspace_id:
            res = [r for r in res if r.workspace_id == str(workspace_id)]
        if dataset_id:
            res = [r for r in res if r.dataset_id == dataset_id]
        res.sort(key=lambda x: x.timestamp, reverse=True)
        return res

    def compare_runs(self, run_a_id: str, run_b_id: str) -> ExperimentComparison | None:
        run_a = self.get_run(run_a_id)
        run_b = self.get_run(run_b_id)
        if not run_a or not run_b:
            return None

        # Config diff
        cfg_a = run_a.config.model_dump()
        cfg_b = run_b.config.model_dump()
        config_diff = {}
        all_keys = set(cfg_a.keys()).union(set(cfg_b.keys()))
        for k in all_keys:
            if cfg_a.get(k) != cfg_b.get(k):
                config_diff[k] = {"run_a": cfg_a.get(k), "run_b": cfg_b.get(k)}

        # Metrics diff
        metrics_diff = {
            "mean_recall_at_k_delta": round(run_b.mean_recall_at_k - run_a.mean_recall_at_k, 4),
            "mean_mrr_delta": round(run_b.mean_mrr - run_a.mean_mrr, 4),
            "mean_ndcg_at_k_delta": round(run_b.mean_ndcg_at_k - run_a.mean_ndcg_at_k, 4),
            "mean_citation_f1_delta": round(run_b.mean_citation_f1 - run_a.mean_citation_f1, 4),
            "mean_latency_ms_delta": round(run_b.mean_latency_ms - run_a.mean_latency_ms, 2),
        }

        return ExperimentComparison(
            run_a_id=run_a.run_id,
            run_b_id=run_b.run_id,
            dataset_id=run_a.dataset_id,
            config_diff=config_diff,
            metrics_diff=metrics_diff,
        )

    def delete_dataset(self, dataset_id: str) -> bool:
        if dataset_id in self._datasets:
            del self._datasets[dataset_id]
            return True
        return False

    def delete_run(self, run_id: str) -> bool:
        if run_id in self._runs:
            del self._runs[run_id]
            return True
        return False

    def clear(self) -> None:
        self._datasets.clear()
        self._runs.clear()


_eval_repo = EvaluationRepository()


def get_evaluation_repository() -> EvaluationRepository:
    return _eval_repo
