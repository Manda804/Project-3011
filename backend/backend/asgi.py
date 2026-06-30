"""
ASGI config for backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import json
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

django_asgi_app = get_asgi_application()


class WebSocketManager:
    def __init__(self):
        self.connections = set()

    async def connect(self, scope, receive, send):
        await send({'type': 'websocket.accept'})
        self.connections.add(send)
        try:
            while True:
                message = await receive()
                if message['type'] == 'websocket.disconnect':
                    break
        finally:
            self.connections.discard(send)

    async def broadcast(self, payload):
        text = json.dumps(payload)
        stale = set()
        for send in list(self.connections):
            try:
                await send({'type': 'websocket.send', 'text': text})
            except Exception:
                stale.add(send)
        self.connections.difference_update(stale)


websocket_manager = WebSocketManager()


class ASGIRouter:
    def __init__(self, http_app):
        self.http_app = http_app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            await self.http_app(scope, receive, send)
            return

        if scope['type'] == 'websocket' and scope['path'] == '/ws/telemetry/':
            await websocket_manager.connect(scope, receive, send)
            return

        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1000})
            return

        await self.http_app(scope, receive, send)


application = ASGIRouter(django_asgi_app)
