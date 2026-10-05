"""API endpoints for Evaluation experiments and Tracing Observability."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_workspace_membership
from app.core.exceptions import BadRequestError, NotFoundError
from app.database.session import get_db
from app.evaluation.models import (
    EvaluationConfig,
    EvaluationDataset,
    EvaluationRun,
    ExperimentComparison,
)
from app.evaluation.repository import get_evaluation_repository
from app.evaluation.runner import EvaluationRunner
from app.models.membership import Membership
from app.models.user import User
from app.observability.repository import get_trace_repository
from app.observability.tracer import Trace

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["Evaluation & Observability"])


# --- DATASETS ---


@router.post(
    "/evaluations/datasets", response_model=EvaluationDataset, status_code=status.HTTP_201_CREATED
)
async def create_dataset(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    dataset: EvaluationDataset,
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
) -> EvaluationDataset:
    """Creates a new evaluation dataset scoped to the workspace."""
    dataset.workspace_id = str(workspace_id)
    repo = get_evaluation_repository()
    repo.save_dataset(dataset)
    return dataset


@router.get("/evaluations/datasets", response_model=list[EvaluationDataset])
async def list_datasets(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
) -> list[EvaluationDataset]:
    """Lists all evaluation datasets in the workspace."""
    repo = get_evaluation_repository()
    return repo.list_datasets(workspace_id=str(workspace_id))


@router.get("/evaluations/datasets/{dataset_id}", response_model=EvaluationDataset)
async def get_dataset(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    dataset_id: Annotated[str, Path(...)],
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
) -> EvaluationDataset:
    """Retrieves an evaluation dataset by ID."""
    repo = get_evaluation_repository()
    ds = repo.get_dataset(dataset_id)
    if not ds or ds.workspace_id != str(workspace_id):
        raise NotFoundError("Evaluation dataset not found in this workspace.")
    return ds


# --- RUNS & BENCHMARKS ---


class RunEvaluationBody(BaseModel):
    dataset_id: str
    retrieval_mode: Literal["semantic", "hybrid"] = "hybrid"
    top_k: int = 5
    enable_reranking: bool = False
    evaluator_mode: Literal["deterministic", "llm_assisted"] = "deterministic"


@router.post("/evaluations/run", response_model=EvaluationRun, status_code=status.HTTP_201_CREATED)
@router.post("/evaluations/runs", response_model=EvaluationRun, status_code=status.HTTP_201_CREATED)
async def run_evaluation(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    body: RunEvaluationBody | None = None,
    dataset_id: str | None = Query(None),
    config: EvaluationConfig = Depends(),
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EvaluationRun:
    """Executes an evaluation run for a dataset under the given configuration."""
    target_dataset_id = body.dataset_id if body else dataset_id
    if not target_dataset_id:
        raise BadRequestError("dataset_id is required either in request body or query parameter.")

    eval_config = config
    if body:
        eval_config = EvaluationConfig(
            retrieval_mode=body.retrieval_mode,
            final_top_k=body.top_k,
            enable_reranking=body.enable_reranking,
            evaluator_mode=body.evaluator_mode,
        )

    repo = get_evaluation_repository()
    dataset = repo.get_dataset(target_dataset_id)
    if not dataset or dataset.workspace_id != str(workspace_id):
        raise NotFoundError("Evaluation dataset not found in this workspace.")

    runner = EvaluationRunner(session=session)
    return await runner.run(dataset=dataset, config=eval_config)


@router.get("/evaluations/runs", response_model=list[EvaluationRun])
async def list_evaluation_runs(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    dataset_id: str | None = Query(None),
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
) -> list[EvaluationRun]:
    """Lists completed evaluation runs for this workspace."""
    repo = get_evaluation_repository()
    return repo.list_runs(workspace_id=str(workspace_id), dataset_id=dataset_id)


@router.get("/evaluations/runs/{run_id}", response_model=EvaluationRun)
async def get_evaluation_run(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    run_id: Annotated[str, Path(...)],
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
) -> EvaluationRun:
    """Retrieves detailed results for a specific evaluation run."""
    repo = get_evaluation_repository()
    run = repo.get_run(run_id)
    if not run or run.workspace_id != str(workspace_id):
        raise NotFoundError("Evaluation run not found in this workspace.")
    return run


@router.get("/evaluations/compare", response_model=ExperimentComparison)
async def compare_experiments(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    run_a_id: str = Query(..., description="Baseline experiment run ID"),
    run_b_id: str = Query(..., description="Comparison experiment run ID"),
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
) -> ExperimentComparison:
    """Compares two evaluation runs (A vs B) and reports config differences and metric deltas."""
    repo = get_evaluation_repository()
    run_a = repo.get_run(run_a_id)
    run_b = repo.get_run(run_b_id)
    if not run_a or run_a.workspace_id != str(workspace_id):
        raise NotFoundError("Run A not found in this workspace.")
    if not run_b or run_b.workspace_id != str(workspace_id):
        raise NotFoundError("Run B not found in this workspace.")

    comparison = repo.compare_runs(run_a_id, run_b_id)
    if not comparison:
        raise NotFoundError("Could not compare the specified runs.")
    return comparison


# --- TRACING OBSERVABILITY ---


@router.get("/traces", response_model=list[Trace])
async def list_traces(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    operation_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
) -> list[Trace]:
    """Lists execution traces recorded for the workspace."""
    trace_repo = get_trace_repository()
    return trace_repo.list_traces(
        workspace_id=str(workspace_id),
        operation_name=operation_name,
        limit=limit,
        offset=offset,
    )


@router.get("/traces/{trace_id}", response_model=Trace)
async def get_trace(
    workspace_id: Annotated[uuid.UUID, Path(...)],
    trace_id: Annotated[str, Path(...)],
    membership: Membership = Depends(get_workspace_membership),
    current_user: User = Depends(get_current_user),
) -> Trace:
    """Inspects a specific execution trace and its detailed span timings."""
    trace_repo = get_trace_repository()
    trace = trace_repo.get_trace(trace_id)
    if not trace or (trace.workspace_id and trace.workspace_id != str(workspace_id)):
        raise NotFoundError("Trace not found in this workspace.")
    return trace
