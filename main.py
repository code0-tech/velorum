import concurrent.futures
import os
import signal
import sys
import time

import grpc

from src.edition import install as _install_edition
_install_edition()

from src.interceptor.auth_interceptor import AuthInterceptor
from src.logger import get_logger

log = get_logger("velorum")

current_dir = os.path.dirname(os.path.abspath(__file__))
venv_site_packages = os.path.join(current_dir, ".venv", "lib", "python3.12", "site-packages")

# 2. Den Pfad hinzufügen, wo 'velorum' als Paket drinliegt
target_path = os.path.join(venv_site_packages, "tucana", "generated")

if target_path not in sys.path:
    sys.path.insert(0, target_path)

import tucana.generated.velorum.generate_pb2_grpc as generate_pb2_grpc
import tucana.generated.velorum.generate_pb2 as generate_pb2
import tucana.generated.velorum.info_pb2_grpc as info_pb2_grpc
import tucana.generated.velorum.info_pb2 as info_pb2
from grpc_reflection.v1alpha import reflection
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from src.endpoint.info.info_endpoint import InfoService
from src.endpoint.generation.generate_endpoint import GenerateService

if __name__ == '__main__':

    server = grpc.server(
        concurrent.futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[AuthInterceptor()]
    )
    generate_pb2_grpc.add_GenerateServiceServicer_to_server(GenerateService(), server)
    info_pb2_grpc.add_InfoServiceServicer_to_server(InfoService(), server)


    health_servicer = health.HealthServicer()
    health_servicer.set('liveness', health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set('readiness', health_pb2.HealthCheckResponse.SERVING)
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    port = os.getenv("HOST", "0.0.0.0") + ":" + os.getenv("PORT", "50051")
    server.add_insecure_port(port)
    log.success(f"Velorum listening on {port}")  # type: ignore[attr-defined]

    SERVICE_NAMES = (
        generate_pb2.DESCRIPTOR.services_by_name['GenerateService'].full_name,
        info_pb2.DESCRIPTOR.services_by_name['InfoService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    server.start()


    def shutdown(signum, frame):
        log.info("Shutting down gracefully...")
        health_servicer.enter_graceful_shutdown()
        server.stop(5).wait()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server.wait_for_termination()
