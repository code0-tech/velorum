"""Local, model-backed test: flow -> flow.

Runs the real ``GenerateService.Flow`` pipeline (an existing flow plus a
modification instruction) and scores the modified flow against a hand-written
expected flow via cosine similarity. Enable with ``VELORUM_LOCAL_MODEL_TESTS=1``.
"""

import json
from pathlib import Path

import pytest

from src.mapper.flow_mapper import map_to_flow_schema
from src.schema.flow_schema import Flow
from tests.local._harness import (
    MODEL_IDENTIFIER,
    SIMILARITY_THRESHOLD,
    FakeContext,
    build_flow_request,
    cosine_similarity,
    flow_to_text,
)

_CASES = json.loads((Path(__file__).parent / "cases" / "flow_to_flow.json").read_text(encoding="utf-8"))


@pytest.mark.local
@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_flow_to_flow(case, service, vector_model):
    input_flow = Flow.model_validate(case["input_flow"])
    request = build_flow_request(case["prompt"], input_flow)

    response = service.Flow(request, FakeContext())
    assert response is not None and response.HasField("flow"), "Flow returned no flow"

    generated_flow = map_to_flow_schema(response.flow)
    expected_flow = Flow.model_validate(case["expected_flow"])

    score = cosine_similarity(vector_model, expected_flow, generated_flow)

    print(f"\n[{case['name']}] similarity={score:.4f} (threshold={SIMILARITY_THRESHOLD})")
    print("--- input ---\n" + flow_to_text(input_flow))
    print("--- expected ---\n" + flow_to_text(expected_flow))
    print("--- generated ---\n" + flow_to_text(generated_flow))

    assert score >= SIMILARITY_THRESHOLD, (
        f"[{case['name']}] model={MODEL_IDENTIFIER} "
        f"similarity {score:.4f} < threshold {SIMILARITY_THRESHOLD}"
    )
