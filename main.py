import concurrent.futures
import os
import sys
import time

import grpc

from src.interceptor.auth_interceptor import AuthInterceptor

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

from src.endpoint.info.info_endpoint import InfoService
from src.endpoint.generation.generate_endpoint import GenerateService

if __name__ == '__main__':

    server = grpc.server(
        concurrent.futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[AuthInterceptor()]
    )
    generate_pb2_grpc.add_GenerateServiceServicer_to_server(GenerateService(), server)
    info_pb2_grpc.add_InfoServiceServicer_to_server(InfoService(), server)

    port = os.getenv("HOST", "0.0.0.0") + ":" + os.getenv("PORT", "50051")
    server.add_insecure_port(port)
    print(f"Velorum GenerateService läuft auf {port}...")

    SERVICE_NAMES = (
        generate_pb2.DESCRIPTOR.services_by_name['GenerateService'].full_name,
        info_pb2.DESCRIPTOR.services_by_name['InfoService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    server.start()

    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        print("\nServer wird sauber heruntergefahren...")
        server.stop(0)
