"""
JSON-RPC 2.0 implementation.
"""

import inspect
import json
from types import UnionType
from typing import (
    Any,
    Callable,
    Literal,
    NotRequired,
    Sequence,
    TypedDict,
    TypeGuard,
    get_args,
    get_origin,
    is_typeddict,
)

_MISSING = '=-=MISSING=-='


class _TD(TypedDict):
    pass


class Request(TypedDict):
    jsonrpc: Literal['2.0']
    id: NotRequired[int | str | None]
    method: str
    params: NotRequired[list | tuple | dict]


class _InnerError(TypedDict):
    code: int
    message: str
    data: NotRequired[Any]


class Result(TypedDict):
    jsonrpc: Literal['2.0']
    id: int | str | None
    result: Any


class Error(TypedDict):
    jsonrpc: Literal['2.0']
    id: int | str | None
    error: _InnerError


type Response = Result | Error


def _validate[T: _TD](value: Any, schema: type[T]) -> TypeGuard[T]:
    if not isinstance(value, dict):
        return False
    schema_dict = inspect.get_annotations(schema)

    for key in schema_dict.keys():
        type_ = schema_dict[key]
        origin = get_origin(type_)
        args = get_args(type_)

        if origin is not NotRequired and key not in value:
            return False
        if origin is NotRequired and key not in value:
            continue
        if type_ is Any or Any in args:
            continue
        if origin is None:
            args = (type_,)

        if origin is Literal:
            if value[key] not in args:
                return False
        elif origin in (None, NotRequired, UnionType):
            if not any(
                isinstance(value[key], schema_or_type)
                if not is_typeddict(schema_or_type)
                else _validate(value[key], schema_or_type)
                for schema_or_type in args
            ):
                return False
        else:
            raise ValueError(f"can't handle type: {type_}")
    return True


def make_request(
    method: str,
    params: list | tuple | dict | None = None,
    *,
    id: int | str | None = _MISSING,
) -> Request:
    """
    Constructs a valid JSON-RPC request.

    Leave `id` empty for a notification request.

    Args:
        method: Name of the method to be invoked.
        params: Parameter values for the method.
        id: Request id.

    Returns:
        JSON-RPC request.
    """
    obj: Request = {
        'jsonrpc': '2.0',
        'method': method,
    }
    if id is not _MISSING:
        obj['id'] = id
    if params is not None:
        obj['params'] = params
    return obj


def make_error_response(
    code: int,
    message: str,
    data: Any | None = None,
    *,
    id: int | str | None,
) -> Error | None:
    """
    Constructs a valid JSON-RPC failed response.

    Args:
        code: Error code.
        message: Error description.
        data: Additional error info.
        id: Request id.

    Returns:
        JSON-RPC response or None if the request was a notification.
    """
    if id is _MISSING:
        return
    obj: Error = {
        'jsonrpc': '2.0',
        'id': id,
        'error': {
            'code': code,
            'message': message,
        },
    }
    if data is not None:
        obj['error']['data'] = data
    return obj


def make_success_response(
    result: Any,
    *,
    id: int | str | None,
) -> Result | None:
    """
    Constructs a valid JSON-RPC successful response.

    Args:
        result: Result value.
        id: Request id.

    Returns:
        JSON-RPC response or None if the request was a notification.
    """
    if id is _MISSING:
        return
    obj: Result = {
        'jsonrpc': '2.0',
        'id': id,
        'result': result,
    }
    return obj


def handle_request(
    request: Request, method_lookup: dict[str, Callable]
) -> Response | None:
    """
    Handles a JSON-RPC request.

    Args:
        request: JSON-RPC request.
        method_lookup: Lookup dictionary for methods.

    Returns:
        JSON-RPC response or None if the request was a notification.
    """
    if not _validate(request, Request):
        return make_error_response(-32600, 'Invalid Request', id=None)

    method = request['method']
    id = request.get('id', _MISSING)
    params = request.get('params', None)

    if method not in method_lookup:
        return make_error_response(-32601, 'Method not found', id=id)

    func = method_lookup[method]
    try:
        if params is None:
            res = func()
        elif isinstance(params, Sequence):
            res = func(*params)
        else:  # elif isinstance(params, dict):
            res = func(**params)
    except TypeError:
        return make_error_response(-32602, 'Invalid params', id=id)
    except Exception as err:
        return make_error_response(
            -32603,
            'Internal error',
            data=f'{type(err).__name__}: {str(err)}',
            id=id,
        )

    return make_success_response(res, id=id)


def handle_batch_request(
    requests: list[Request], method_lookup: dict[str, Callable]
) -> list[Response] | None:
    """
    Handles a batch JSON-RPC request.

    Args:
        request: List of JSON-RPC requests.
        method_lookup: Lookup dictionary for methods.

    Returns:
        JSON-RPC responses or None if all the requests are notifications.
    """
    responses = [
        handle_request(request, method_lookup) for request in requests
    ]
    filtered = [response for response in responses if response]
    return filtered if filtered else None


def process_request(
    bytes_: bytes, method_lookup: dict[str, Callable]
) -> Response | list[Response] | None:
    """
    Parses the request from bytes and handles it.

    Args:
        bytes_: Request bytes.
        method_lookup: Lookup dictionary for methods.

    Returns:
        JSON-RPC response(s) or None if all the requests are notifications.
    """
    try:
        request = json.loads(bytes_)
    except json.JSONDecodeError:
        return make_error_response(-32700, 'Parse error', id=None)

    if isinstance(request, list):
        response = handle_batch_request(request, method_lookup)
    else:
        response = handle_request(request, method_lookup)
    return response


def serialize(value: Any) -> bytes:
    """Serializes a value."""
    return json.dumps(value).encode()
