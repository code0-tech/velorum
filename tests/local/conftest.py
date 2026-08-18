"""Pytest fixtures for the local, model-backed generation tests.

Importing ``_harness`` first performs the sys.path setup the generated tucana
protobuf modules require, so it must stay at the top.
"""

import os

import pytest

import tests.local._harness  # noqa: F401 - ensures tucana sys.path setup runs first


def pytest_collection_modifyitems(config, items):
    """Skip the model-backed ``local`` tests when running in CI.

    They call a real LLM, so they must not run on CI. The standard ``CI``
    environment variable (set automatically by GitHub Actions, GitLab CI, etc.)
    is used to detect that — no project-specific variable is introduced. Locally,
    where ``CI`` is unset, a plain ``pytest`` run executes them.
    """
    if not os.environ.get("CI"):
        return
    skip_ci = pytest.mark.skip(reason="model-backed local test skipped in CI (CI env var set)")
    for item in items:
        if "local" in item.keywords:
            item.add_marker(skip_ci)


@pytest.fixture(scope="session")
def service():
    """A fully initialised ``GenerateService`` (vector stores, few-shots, models).

    Built once per session because loading the embedding model and seeding the
    in-memory Qdrant stores is expensive.
    """
    from src.endpoint.generation.generate_endpoint import GenerateService

    return GenerateService()


@pytest.fixture(scope="session")
def vector_model(service):
    """Reuse the service's embedding model for the similarity metric."""
    return service.vector_model
