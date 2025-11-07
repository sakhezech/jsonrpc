import asyncio
import socket

import httpx
import requests

import jsonrpc

HOST = 'localhost'
PORT = 4999


to_send = [
    jsonrpc.Request('sum_numbers', [1, 2, 3, 4, 5], id=0),
    jsonrpc.Request('say_hello', ['USER'], id=1),
    jsonrpc.Request('sleep', [2], id=2),
    jsonrpc.Request('sleep', [2], id=3),
    jsonrpc.Request('crash_on_call', id=4),
    jsonrpc.Request('sum_numbers', ['type', 'error'], id=5),
    jsonrpc.Request('say_hello', {'world': 'wrong param name'}, id=6),
    jsonrpc.Request('say_hello', ['wrong', 'param', 'count'], id=7),
    jsonrpc.Request('say_hello', ['this is a notification']),
    jsonrpc.Request(
        batch=[
            jsonrpc.Request('sum_numbers', [0, -1], id=8),
            jsonrpc.Request('crash_on_call', id=9),
            jsonrpc.Request('say_hello', ['world'], id=8),
        ]
    ),
]


def print_response(response: jsonrpc.Response) -> None:
    if not response.is_error():
        print(response.id, response.result())
    else:
        print(response.id, response.message, response.data)


async def httpx_client() -> None:
    client = httpx.AsyncClient(base_url=f'http://{HOST}:{PORT}')
    httpx_responses = await asyncio.gather(
        *[
            client.post('/jsonrpc', content=request.serialize())
            for request in to_send
        ]
    )
    bodies = [httpx_response.read() for httpx_response in httpx_responses]
    responses = [jsonrpc.Response.deserialize(body) for body in bodies if body]
    for response in responses:
        print_response(response)


def requests_client() -> None:
    for request in to_send:
        body = requests.post(
            f'http://{HOST}:{PORT}/jsonrpc', data=request.serialize()
        ).content
        if body:
            response = jsonrpc.Response.deserialize(body)
            print_response(response)


async def async_socket_client() -> None:
    async def do(request: jsonrpc.Request) -> jsonrpc.Response | None:
        reader, writer = await asyncio.open_connection(HOST, PORT)
        writer.write(request.serialize())
        body = await reader.read()
        if body:
            response = jsonrpc.Response.deserialize(body)
            return response

    responses = await asyncio.gather(*[do(req) for req in to_send])
    for response in responses:
        if response:
            print_response(response)


def sync_socket_client() -> None:
    def do(request: jsonrpc.Request) -> jsonrpc.Response | None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((HOST, PORT))
            sock.sendall(request.serialize())
            body = sock.recv(2**12)
            if body:
                response = jsonrpc.Response.deserialize(body)
                return response

    for request in to_send:
        response = do(request)
        if response:
            print_response(response)


if __name__ == '__main__':
    import argparse

    variants = {
        'httpx': httpx_client,
        'requests': requests_client,
        'sync_socket': sync_socket_client,
        'async_socket': async_socket_client,
    }

    parser = argparse.ArgumentParser()
    parser.add_argument('client', choices=variants.keys())
    args = parser.parse_args(None)

    client = variants[args.client]
    if asyncio.iscoroutinefunction(client):
        asyncio.run(client())
    else:
        client()
