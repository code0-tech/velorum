"""Shared helpers for the local, model-backed generation tests.

These tests exercise the *real* pipeline: vector-store retrieval, the LLM
orchestration (prompt -> flow and flow -> flow) and the postprocessing — exactly
as the gRPC ``GenerateService`` runs it. They therefore require a reachable model
with valid credentials and only run when the ``local`` marker is selected
explicitly (``pytest -m local``); a plain run in CI deselects them.

The generated flow is compared to a hand-written expected flow via cosine
similarity of their embeddings, so small, non-deterministic wording differences
in the model output do not make the tests flaky.
"""

import sys
from pathlib import Path
from typing import List, Tuple

# The generated tucana protobuf modules use absolute imports such as
# ``from shared import struct_pb2`` — the same sys.path setup that ``main.py`` and
# ``cli/cli.py`` perform is required before importing anything proto-backed.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VENV_SITE_PACKAGES = PROJECT_ROOT / ".venv" / "lib" / "python3.12" / "site-packages"
_TUCANA_GENERATED = _VENV_SITE_PACKAGES / "tucana" / "generated"

for _path in (str(PROJECT_ROOT), str(_TUCANA_GENERATED)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import numpy as np
import tucana.generated.velorum.generate_pb2 as pb2

from cli.cli import FlowGeneratorCLI
from src.mapper.data_type_mapper import map_to_grpc_data_type
from src.mapper.flow_mapper import map_to_grpc_flow
from src.mapper.flow_types_mapper import map_to_grpc_flow_type
from src.mapper.function_mapper import map_to_grpc_function
from src.schema.flow_schema import Flow, NodeParameterValue

# The model identifier must exist in ``models.configuration.json``; the threshold
# is the minimum cosine similarity for a case to pass. Adjust here if needed.
MODEL_IDENTIFIER = "gpt-oss-120b"
SIMILARITY_THRESHOLD = 0.85
PROJECT_ID = 424242


def load_definitions() -> Tuple[list, list, list]:
    """Load the project's data types, flow types and functions from the CLI fixtures."""
    cli = FlowGeneratorCLI()
    data_types, flow_types, functions = cli.load_all()
    return data_types, flow_types, functions


def build_prompt_request(prompt: str) -> pb2.PromptRequest:
    data_types, flow_types, functions = load_definitions()
    return pb2.PromptRequest(
        prompt=prompt,
        project_id=PROJECT_ID,
        model_identifier=MODEL_IDENTIFIER,
        flow_types=[map_to_grpc_flow_type(ft) for ft in flow_types],
        functions=[map_to_grpc_function(fn) for fn in functions],
        data_types=[map_to_grpc_data_type(dt) for dt in data_types],
    )


def build_flow_request(prompt: str, flow: Flow) -> pb2.FlowRequest:
    data_types, flow_types, functions = load_definitions()
    return pb2.FlowRequest(
        prompt=prompt,
        project_id=PROJECT_ID,
        model_identifier=MODEL_IDENTIFIER,
        flow=map_to_grpc_flow(flow),
        flow_types=[map_to_grpc_flow_type(ft) for ft in flow_types],
        functions=[map_to_grpc_function(fn) for fn in functions],
        data_types=[map_to_grpc_data_type(dt) for dt in data_types],
    )


class _AbortError(RuntimeError):
    """Raised by :class:`FakeContext` so an aborted RPC surfaces as a test failure."""


class FakeContext:
    """Minimal stand-in for a gRPC servicer context.

    The real endpoint calls ``context.abort(code, details)`` on any rejection;
    turning that into an exception makes a rejected request fail the test loudly
    instead of silently returning ``None``.
    """

    def abort(self, code, details):  # noqa: D401 - mirrors grpc signature
        raise _AbortError(f"{code}: {details}")


def _param_to_text(parameter: NodeParameterValue) -> str:
    """Flatten a single parameter into a stable, semantic text fragment.

    Node ids are intentionally omitted: they are assigned freely by the model and
    would only add noise to the embedding. Inline references contribute their
    signature and nested value so the ``${...}`` feature is reflected in the score.
    """
    parts: List[str] = []
    value = getattr(parameter, "value", None)
    if value is not None or hasattr(parameter, "value"):
        parts.append(f"literal={value!r}")

    references = getattr(parameter, "references", None)
    for reference in references or []:
        parts.append(f"ref[{reference.signature}]=({_param_to_text(reference.value)})")

    if getattr(parameter, "reference_path", None):
        joined = "/".join(p.path for p in parameter.reference_path if p.path)
        parts.append(f"path={joined}")
    if getattr(parameter, "starting_node_id", None) is not None:
        parts.append("subflow")
    if getattr(parameter, "input_index", None) is not None:
        parts.append("input_reference")
    elif getattr(parameter, "node_id", None) is not None:
        parts.append("node_reference")

    return " ".join(parts) if parts else "empty"


def flow_to_text(flow: Flow) -> str:
    """Canonical, id-independent text representation used for the embedding.

    Focuses on the semantically meaningful parts of a flow — its type, the ordered
    functions and each parameter's shape — so cosine similarity measures whether
    the model produced the *right kind* of flow rather than an exact string match.
    """
    lines = [f"type: {flow.type}", f"name: {flow.name}"]
    for node in flow.nodes:
        lines.append(f"function: {node.function_identifier}")
        for parameter in node.parameters or []:
            lines.append(f"  param: {_param_to_text(parameter)}")
    for index, setting in enumerate(flow.settings or []):
        lines.append(f"setting[{index}]: {setting.value!r}")
    return "\n".join(lines)


def cosine_similarity(vector_model, expected: Flow, actual: Flow) -> float:
    """Cosine similarity of the two flows' embeddings, computed with the same
    model2vec model the service uses for retrieval."""
    embeddings = vector_model.encode([flow_to_text(expected), flow_to_text(actual)])
    expected_vec = np.asarray(embeddings[0], dtype=np.float64)
    actual_vec = np.asarray(embeddings[1], dtype=np.float64)
    denominator = np.linalg.norm(expected_vec) * np.linalg.norm(actual_vec)
    if denominator == 0:
        return 0.0
    return float(np.dot(expected_vec, actual_vec) / denominator)
