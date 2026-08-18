# Local model-backed generation tests

These tests exercise the **real** generation pipeline end to end:

- `test_prompt_to_flow.py` → `GenerateService.Prompt` (prompt → flow)
- `test_flow_to_flow.py` → `GenerateService.Flow` (existing flow + instruction → flow)

Each test builds a real gRPC request from the fixtures in `cli/` (data types,
flow types, functions), runs vector-store retrieval + LLM orchestration +
postprocessing exactly as the server does, and scores the generated flow against
a hand-written expected flow using **cosine similarity** of their embeddings
(same `model2vec` model the service uses for retrieval).

## Why they are local-only

They call a real language model. They carry the `local` pytest marker and are
**automatically skipped in CI**: the conftest skips them whenever the standard
`CI` environment variable is set (GitHub Actions, GitLab CI, … set it for you).
No project-specific variable is introduced.

## Running

Locally (`CI` unset) a plain run executes them:

```bash
# from the project root
uv run pytest tests/local -v -s
```

Run only these tests via the marker:

```bash
uv run pytest -m local -v -s
```

## Configuration

No environment variables. The model identifier and similarity threshold are
constants at the top of `_harness.py`:

| Constant               | Default        | Meaning                                              |
| ---------------------- | -------------- | ---------------------------------------------------- |
| `MODEL_IDENTIFIER`     | `gpt-oss-120b` | `identifier` from `models.configuration.json` to use.|
| `SIMILARITY_THRESHOLD` | `0.85`         | Minimum cosine similarity for a case to pass.        |

## Adding cases

Drop new entries into `cases/prompt_to_flow.json` or `cases/flow_to_flow.json`.

- prompt → flow: `{ "name", "prompt", "expected_flow" }`
- flow → flow: `{ "name", "prompt", "input_flow", "expected_flow" }`

Flows use the normal schema aliases (`functionIdentifier`, `nodeFunctionId`,
`referencePath`, `startingNodeId`, …). Inline references are supported via a
literal's `references` list, e.g.:

```json
{
  "value": "Hallo ${user name}!",
  "references": [
    { "signature": "user name",
      "value": { "nodeFunctionId": 0, "referencePath": [{ "path": "name" }] } }
  ]
}
```

The comparison is intentionally id-independent and structural (see
`flow_to_text` in `_harness.py`): it rewards producing the right flow type,
functions, parameter shapes and inline references rather than an exact string
match — which keeps the tests robust against normal model non-determinism.
