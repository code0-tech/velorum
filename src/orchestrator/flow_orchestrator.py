from typing import List, Any

import instructor
from litellm import completion
from litellm.types.completion import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from src.schema.flow_schema import Flow
from src.schema.flow_type_schema import FlowType
from src.schema.function_schema import FunctionDefinition
from src.schema.model_schema import Model


class FlowOrchestrator:
    def __init__(self):
        self.client = instructor.from_litellm(completion, mode=instructor.Mode.MD_JSON)

    def generate(
            self,
            model: Model,
            prompt: str,
            flow: Flow,
            few_shots: List[ChatCompletionUserMessageParam],
            available_flow_types: List[FlowType],
            available_functions: List[FunctionDefinition]
    ) -> tuple[Flow, Any]:
        flow_types_json = [f"{t.identifier}{t.signature}" for t in available_flow_types]
        functions_json = [f"{f.identifier}{f.signature}" for f in available_functions]

        messages = [
            ChatCompletionSystemMessageParam(
                role="system",
                content=(
                    "You are a raw JSON output engine. "
                    "CRITICAL: Output ONLY valid JSON. "
                    "Do not explain. Do not return the schema definition, return a populated instance of the schema.\n\n"
                    "You are MODIFYING an existing Flow based on the user's instructions. "
                    "Keep unchanged parts intact and only apply the requested updates.\n\n"
                    f"CHOOSE TYPE from: {flow_types_json}\n"
                    f"USE FUNCTIONS from: {functions_json}\n"
                )
            ),
            *few_shots,
            ChatCompletionUserMessageParam(
                role="user",
                content=(
                    f"Current Flow:\n{flow.model_dump_json(indent=2)}\n\n"
                    f"Instruction for modification: {prompt}\n\n"
                    "Generate the updated Flow in JSON format."
                )
            ),
            {"role": "assistant", "content": "{"}
        ]

        flow, completion = self.client.chat.completions.create_with_completion(
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

        return flow, completion
