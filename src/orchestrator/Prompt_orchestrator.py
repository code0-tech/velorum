import os
from typing import List

import instructor
from litellm import completion
from litellm.types.completion import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from src.schema.FlowType_schema import FlowType
from src.schema.Flow_schema import Flow
from src.schema.Function_schema import FunctionDefinition

llm_api_key = os.getenv("LLM_API_KEY")
llm_api_base = os.getenv("LLM_API_BASE")
llm_api_model = os.getenv("LLM_PROVIDER")


class PromptOrchestrator:
    def __init__(self):
        self.client = instructor.from_litellm(completion, mode=instructor.Mode.MD_JSON)
        self.model = llm_api_model

    def generate(
            self,
            prompt: str,
            available_flow_types: List[FlowType],
            available_functions: List[FunctionDefinition]
    ) -> Flow:
        flow_types_json = [t.model_dump(by_alias=True) for t in available_flow_types]
        functions_json = [f.model_dump(by_alias=True) for f in available_functions]

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
            ChatCompletionUserMessageParam(
                role="user",
                content=f"Generate a Flow for: {prompt} in JSON format"
            )
        ]

        print("messages", messages)

        flow, completion = self.client.chat.completions.create_with_completion(
            model=self.model,
            response_model=Flow,
            api_key=llm_api_key,
            api_base=llm_api_base,
            messages=messages,
            max_retries=3,
            strict=True,
            timeout=20,
            top_p=0,
            temperature=0.0,
        )

        return flow
