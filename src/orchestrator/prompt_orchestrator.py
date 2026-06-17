from typing import List, Any, Dict

import instructor
from litellm import completion
from litellm.types.completion import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from src.logger import get_logger
from src.schema.flow_schema import Flow
from src.schema.flow_type_schema import FlowType
from src.schema.function_schema import FunctionDefinition
from src.schema.model_schema import Model

log = get_logger("prompt_orchestrator")


class PromptOrchestrator:
    def __init__(self):
        self.client = instructor.from_litellm(completion, mode=instructor.Mode.MD_JSON)

    def generate(
            self,
            model: Model,
            prompt: str,
            few_shots: List[Dict],
            available_flow_types: List[FlowType],
            available_functions: List[FunctionDefinition]
    ) -> tuple[Flow, Any]:
        flow_types_json = [f"{t.identifier}{t.signature}" for t in available_flow_types]
        functions_json = [f"{f.identifier}{f.signature}" for f in available_functions]

        few_shot_pairs = len(few_shots) // 2
        log.debug(
            f"Building prompt — model={model.provider} "
            f"functions={len(available_functions)} "
            f"flow_types={len(available_flow_types)} "
            f"few_shot_pairs={few_shot_pairs}"
        )

        messages = [
            ChatCompletionSystemMessageParam(
                role="system",
                content=(
                    "You are a raw JSON output engine. "
                    "CRITICAL: Output ONLY valid JSON. "
                    "Do not explain. Do not return the schema definition, return a populated instance of the schema.\n\n"
                    f"CHOOSE TYPE from: {flow_types_json}\n"
                    f"USE FUNCTIONS from: {functions_json}\n"
                )
            ),
            *few_shots,
            ChatCompletionUserMessageParam(
                role="user",
                content=f"Generate a Flow for: {prompt} in JSON format"
            ),
            {"role": "assistant", "content": "{"}
        ]

        log.debug(f"Sending {len(messages)} messages to {model.provider} (max_retries=5)")

        flow, comp = self.client.chat.completions.create_with_completion(
            model=model.provider,
            response_model=Flow,
            api_key=model.auth,
            api_base=model.api,
            messages=messages,
            max_retries=5,
            strict=True,
            timeout=60,
            max_tokens=50000,
            top_p=0.1,
            temperature=0.0,
            include_reasoning=False,
        )

        log.debug(
            f"Completion received — "
            f"prompt_tokens={comp.usage.prompt_tokens} "
            f"completion_tokens={comp.usage.completion_tokens} "
            f"total={comp.usage.total_tokens}"
        )

        return flow, comp
