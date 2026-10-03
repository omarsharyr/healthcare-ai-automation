"""Small local-demo HTTP boundaries; these are not user authentication."""
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class LocalWriteBoundary:
    def __init__(self, app: ASGIApp, max_bytes: int = 65536) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or scope['method'] in ('GET', 'HEAD', 'OPTIONS'):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get('origin')
        error = None
        if origin and origin != f"{scope['scheme']}://{headers.get('host', '')}":
            error = (403, 'Cross-origin writes are not allowed')
        length = headers.get('content-length')
        if not error and length:
            try:
                if int(length) < 0:
                    raise ValueError()
                if int(length) > self.max_bytes:
                    error = (413, 'Request body too large')
            except ValueError:
                error = (400, 'Invalid request length')
        if error:
            await JSONResponse({'detail': error[1]}, status_code=error[0])(scope, receive, send)
            return
        # Count actual streamed bytes as well as Content-Length; never trust that header alone.
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > self.max_bytes:
                await JSONResponse({'detail': 'Request body too large'}, status_code=413)(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get('more_body', False):
                break
        if size and headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
            await JSONResponse({'detail': 'Use application/json'}, status_code=415)(scope, receive, send)
            return
        consumed = False

        async def replay() -> dict:
            nonlocal consumed
            if not consumed:
                consumed = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await receive()

        await self.app(scope, replay, send)
