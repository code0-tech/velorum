from typing import List, Any

from litellm import completion
import instructor
import os

from litellm.types.completion import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from src.schema.FlowType_schema import FlowType
from src.schema.Function_schema import FunctionDefinition
from src.schema.Flow_schema import Flow

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
                    "You are a configuration generator. "
                    "Return ONLY raw JSON that matches the Flow schema. "
                    "Do not explain. Do not return the schema definition, return a populated instance of the schema.\n\n"
                    f"CHOOSE TYPE from: {flow_types_json}\n"
                    f"USE FUNCTIONS from: {functions_json}\n"
                )
            ),
            ChatCompletionUserMessageParam(
                role="user",
                content=prompt
            )
        ]

        print(llm_api_key, llm_api_base, llm_api_model)

        flow, completion = self.client.chat.completions.create_with_completion(
            model=self.model,
            response_model=Flow,
            api_key=llm_api_key,
            api_base=llm_api_base,
            messages=messages,
            max_retries=3,
            strict=True,
            timeout=20,
        )

        return flow