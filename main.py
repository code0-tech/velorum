# Press the green button in the gutter to run the script.
from src.orchestrator.Prompt_orchestrator import PromptOrchestrator
from src.schema.FlowType_schema import FlowType
from src.store.Function_store import FunctionStore

if __name__ == '__main__':
    # function store
    function_store = FunctionStore()
    function_store.insert_from_json("./test/functions.json")

    # orchestrator
    prompt_orchestrator = PromptOrchestrator()

    prompt = "Erstelle einen HTTP Event Flow, der zuerst den Request loggt und dann 'Event empfangen' an Slack sendet."
    results = function_store.search(
        prompt=prompt,
        limit=5
    )

    generated_flow = prompt_orchestrator.generate(
        prompt=prompt,
        available_functions=results,
        available_flow_types=[
            FlowType(
                identifier="http_event_flow",
                names="HTTP Event Flow",
                descriptions="Ein Flow, der durch HTTP-Events ausgelöst wird.",
                signature="(): void",
            )
        ],
    )

    print(generated_flow.model_dump_json(indent=2, by_alias=True, exclude_none=True))
