# JSONRPC

JSONRPC 2.0 Request and Response primitives.

There is no transport implementation, you can pair it with whatever you want.

## Example

For real examples go [to the examples directory](./examples/).

```python
from jsonrpc import Request, Response

# client
request = Request('say_hello', ['world'], id=0)
req_body = request.serialize()
send(req_body)

# server
req_body = receive()

request = Request.deserialize(req_body)
response = request.resolve(method_lookup)  # .resolve_async(...) for async

if response:
    send(response.serialize())
else:
    send(b'')


# client
res_body = receive()
if res_body:
    response = Response.deserialize(res_body)
    if not response.is_error():
        print(response.result())
    else:
        print(response.code, response.message, response.data)
```
