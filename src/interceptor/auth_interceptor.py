import os

import grpc
import jwt

VALID_TOKEN = os.getenv('SECURITY_TOKEN', 'velorum-internal-communication-secret')

class AuthInterceptor(grpc.ServerInterceptor):

    def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata or [])
        auth_token = metadata.get('authorization', '')

        if not auth_token:
            return self._abort_handler()

        try:
            jwt.decode(
                auth_token,
                VALID_TOKEN,
                algorithms=['HS256']
            )
        except Exception as e:
            print(e)
            return self._abort_handler()

        return continuation(handler_call_details)

    def _abort_handler(self, details="Invalid or missing authentication token"):
        def abort_handler(request, context):
            context.abort(
                code=grpc.StatusCode.UNAUTHENTICATED,
                details=details
            )

        return grpc.unary_unary_rpc_method_handler(abort_handler)
