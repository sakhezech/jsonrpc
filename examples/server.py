import asyncio
import socket
import socketserver

import flask
import starlette
import starlette.applications
import starlette.requests
import starlette.responses
import starlette.routing
import uvicorn
from methods import async_method_lookup, sync_method_lookup

import jsonrpc

HOST = 'localhost'
PORT = 4999


async def starlette_server() -> None:
    async def rpc(
        request: starlette.requests.Request,
    ) -> starlette.responses.Response:
        request_ = jsonrpc.Request.deserialize(await request.body())
        response = await request_.resolve_async(async_method_lookup)
        return starlette.responses.Response(
            response.serialize() if response else b'',
            media_type='application/json',
        )

    app = starlette.applications.Starlette(
        routes=[starlette.routing.Route('/jsonrpc', rpc, methods=['POST'])]
    )
    await uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT)).serve()


def flask_server() -> None:
    app = flask.Flask(__file__)

    def rpc():
        body = flask.request.get_data()
        response = jsonrpc.Request.deserialize(body).resolve(
            sync_method_lookup
        )
        return response.serialize() if response else b''

    app.add_url_rule('/jsonrpc', view_func=rpc, methods=['POST'])

    app.run(HOST, PORT)


async def async_socket_server() -> None:
    async def handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        request = jsonrpc.Request.deserialize(await reader.read(2**12))
        response = await request.resolve_async(async_method_lookup)
        if response:
            writer.write(response.serialize())

    server = await asyncio.start_server(handler, HOST, PORT)
    async with server:
        await server.serve_forever()


def sync_socket_server() -> None:
    class JsonRPCSocketHandler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            self.request: socket.socket
            send = self.request.sendall

            req_body = self.request.recv(2**12)
            request = jsonrpc.Request.deserialize(req_body)
            result = request.resolve(sync_method_lookup)
            if result is not None:
                send(result.serialize())

    with socketserver.TCPServer((HOST, PORT), JsonRPCSocketHandler) as server:
        server.serve_forever()


if __name__ == '__main__':
    import argparse

    variants = {
        'starlette': starlette_server,
        'flask': flask_server,
        'sync_socket': sync_socket_server,
        'async_socket': async_socket_server,
    }

    parser = argparse.ArgumentParser()
    parser.add_argument('server', choices=variants.keys())
    args = parser.parse_args(None)

    server = variants[args.server]
    if asyncio.iscoroutinefunction(server):
        asyncio.run(server())
    else:
        server()
