import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
venv_site_packages = os.path.join(project_root, ".venv", "lib", "python3.12", "site-packages")
if project_root not in sys.path:
    sys.path.insert(0, project_root)

target_path = os.path.join(venv_site_packages, "tucana", "generated")

if target_path not in sys.path:
    sys.path.insert(0, target_path)

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List

from src.mapper.data_type_mapper import map_to_grpc_data_type
from src.mapper.function_mapper import map_to_grpc_function
from src.mapper.flow_types_mapper import map_to_grpc_flow_type
import tucana.generated.velorum.generate_pb2 as pb2
from google.protobuf.json_format import MessageToJson

from src.schema.data_type_schema import DataType
from src.schema.flow_type_schema import FlowType, FlowTypeSetting
from src.schema.function_schema import FunctionDefinition, ParameterDefinition


class FlowGeneratorCLI:

    def __init__(self):
        self.cli_dir = Path(__file__).parent
        self.data_types: List[DataType] = []
        self.flow_types: List[FlowType] = []
        self.functions: List[FunctionDefinition] = []

    def load_json_file(self, filename: str) -> List[dict]:
        filepath = self.cli_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_data_types(self) -> List[DataType]:
        raw_data = self.load_json_file("datatypes.json")
        self.data_types = [DataType(
            identifier=item["identifier"],
            type=item["type"],
            genericKeys=item["genericKeys"],
        ) for item in raw_data]
        print(f"Loaded {len(self.data_types)} DataTypes")
        return self.data_types

    def load_flow_types(self) -> List[FlowType]:
        raw_data = self.load_json_file("flowtypes.json")
        self.flow_types = [FlowType(
            identifier=item["identifier"],
            signature=item["signature"],
            names=item["names"][0]["content"],
            aliases=item["aliases"][0]["content"],
            descriptions=item["descriptions"][0]["content"],
            flowTypeSettings=[
                FlowTypeSetting(
                    names=item["names"][0]["content"],
                    descriptions=item["descriptions"][0]["content"],
                    defaultValue=item["defaultValue"] if "defaultValue" in item else None,
                )
                for item in item["flowTypeSettings"]
            ]
        ) for item in raw_data]
        print(f"Loaded {len(self.flow_types)} FlowTypes")
        return self.flow_types

    def load_functions(self) -> List[FunctionDefinition]:
        raw_data = self.load_json_file("functions.json")
        self.functions = [FunctionDefinition(
            identifier=item["identifier"],
            signature=item["signature"],
            names=item["names"][0]["content"],
            aliases=item["aliases"][0]["content"],
            descriptions=item["descriptions"][0]["content"],
            parameterDefinitions=[
                ParameterDefinition(
                    names=item["names"][0]["content"],
                    descriptions=item["descriptions"][0]["content"],
                    defaultValue=item["defaultValue"] if "defaultValue" in item else None,
                )
                for item in item["parameterDefinitions"]["nodes"]
            ]
        ) for item in raw_data]
        print(f"Loaded {len(self.functions)} Functions")
        return self.functions

    def load_all(self) -> tuple:
        self.load_data_types()
        self.load_flow_types()
        self.load_functions()
        return self.data_types, self.flow_types, self.functions

    def run(self, prompt: str, project_id: str, output_file: str = None):
        print("Starting PromptRequest generation...")
        data_types, flow_types, functions = self.load_all()

        output_filename = output_file or f"flow_request_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_path = Path.cwd() / output_filename

        request = pb2.PromptRequest(
            prompt=prompt,
            project_id=int(project_id),
            flow_types=[map_to_grpc_flow_type(ft) for ft in flow_types],
            functions=[map_to_grpc_function(f) for f in functions],
            data_types=[map_to_grpc_data_type(dt) for dt in data_types],
        )

        request_json = json.loads(
            MessageToJson(
                request,
                preserving_proto_field_name=True,
                indent=2
            )
        )

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(request_json, f, indent=2, ensure_ascii=False)

        print(f"PromptRequest generated and saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate Flow requests for Insomnia',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            Examples:
              python cli.py --prompt "Create a REST endpoint" --project-id "proj-123"
              python cli.py --prompt "Generate a cron job" --project-id "proj-123" --output my_flow.json
              python cli.py --prompt "Build data pipeline" --project-id "proj-456" --no-preview
        """
    )

    parser.add_argument(
        '--prompt', '-p',
        type=str,
        required=True,
        help='The prompt describing the flow to generate'
    )

    parser.add_argument(
        '--project-id', '-id',
        type=str,
        required=True,
        help='The project ID for this flow'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Output filename (default: flow_request_TIMESTAMP.json)'
    )

    args = parser.parse_args()

    cli = FlowGeneratorCLI()
    cli.run(
        prompt=args.prompt,
        project_id=args.project_id,
        output_file=args.output
    )


if __name__ == '__main__':
    main()
