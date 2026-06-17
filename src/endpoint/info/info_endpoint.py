import tucana.generated.velorum.info_pb2 as pb2
import tucana.generated.velorum.info_pb2_grpc as pb2_grpc

from src.logger import get_logger
from src.mapper.model_mapper import map_to_grpc_model
from src.store.model_store import ModelStore

log = get_logger("info_endpoint")


class InfoService(pb2_grpc.InfoServiceServicer):
    def __init__(self):
        self.model_store = ModelStore()

    def Models(self, request: pb2.ModelsRequest, context) -> pb2.ModelsResponse:
        models = self.model_store.get_all()
        log.debug(f"[Models] Returning {len(models)} model(s)")
        return pb2.ModelsResponse(models=[map_to_grpc_model(model) for model in models])
