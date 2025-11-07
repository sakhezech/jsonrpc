import asyncio
import json
from types import NoneType, UnionType
from typing import (
    Any,
    Awaitable,
    Callable,
    Self,
    Sequence,
    overload,
)


class JSONRPCError(Exception): ...


class ParseError(JSONRPCError): ...


class InvalidRequestError(JSONRPCError): ...


class MethodNotFoundError(JSONRPCError): ...


class InvalidParamsError(JSONRPCError): ...


class InternalError(JSONRPCError): ...


class ServerError(JSONRPCError): ...


_MISSING = '=-=MISSING=-='
_PARSE_ERROR = '=-=PARSE_ERROR=-='
_INVALID_REQUEST = '=-=INVALID_REQUEST=-='
_BATCH = '=-=BATCH=-='
_err_types: dict[int, type[JSONRPCError]] = {
    -32700: ParseError,
    -32600: InvalidRequestError,
    -32601: MethodNotFoundError,
    -32602: InvalidParamsError,
    -32603: InternalError,
    -32000: ServerError,
}
_request_schema = {
    'jsonrpc': '2.0',
    'method': str,
    'id?': int | str | NoneType,
    'params?': list | tuple | dict,
}
_response_schema = {
    'jsonrpc': '2.0',
    'id': int | str | NoneType,
    'result?': Any,
    'error?': {'code': int, 'message': str, 'data?': Any},
}


def _validate_schema(obj: Any, schema: dict[str, Any]) -> bool:
    if not isinstance(obj, dict):
        return False
    all_keys = [key.removesuffix('?') for key in schema]
    required_keys = [key for key in schema if not key.endswith('?')]
    if not (
        all(key in obj for key in required_keys)
        and all(key in all_keys for key in obj)
    ):
        return False
    for key, type_ in schema.items():
        if type_ is Any:
            continue
        if key.endswith('?'):
            key = key.removesuffix('?')
            if key not in obj:
                continue
        value = obj[key]
        if isinstance(type_, type | UnionType):
            if not isinstance(value, type_):
                return False
        elif isinstance(type_, dict):
            if not _validate_schema(value, type_):
                return False
        else:
            if value != type_:
                return False
    return True


def _dump_if_can(obj: Any) -> Any:
    if hasattr(obj, 'dump'):
        return obj.dump()
    raise TypeError


class Response:
    @overload
    def __init__(self, *, result: Any, id: int | str | None): ...
    @overload
    def __init__(
        self,
        *,
        code: int,
        message: str,
        data: Any | None = None,
        id: int | str | None,
    ): ...
    def __init__(
        self,
        *,
        result: Any = _MISSING,
        code: int | None = None,
        message: str | None = None,
        data: Any | None = None,
        id: int | str | None,
    ) -> None:
        if not ((result is _MISSING) ^ (code is None)):
            raise InternalError(
                f'both result and code are set or unset: '
                f'result={result} code={code}'
            )
        self._result = result
        self.code = code
        self.message = message
        self.data = data
        self.id = id

    def result(self) -> Any:
        self.raise_if_error()
        return self._result

    def is_error(self) -> bool:
        return self.code is not None

    def raise_if_error(self) -> None:
        if self.code is not None:
            raise _err_types[self.code](self.data or self.message)

    def dump(self) -> Any:
        if not self.is_error():
            if self.id is _BATCH:
                return self.result()
            return {
                'jsonrpc': '2.0',
                'id': self.id,
                'result': self.result(),
            }
        else:
            err = {
                'jsonrpc': '2.0',
                'id': self.id,
                'error': {
                    'code': self.code,
                    'message': self.message,
                },
            }
            if self.data is not None:
                err['error']['data'] = self.data
            return err

    @classmethod
    def load(cls, dict_: dict) -> Self:
        if _validate_schema(dict_, _response_schema):
            dict_ = dict_.copy()
            dict_.pop('jsonrpc')
            if 'error' in dict_:
                dict_ |= dict_.pop('error')
            return cls(**dict_)
        raise InternalError(f'this is not a valid response: {dict_}')

    def serialize(self) -> bytes:
        return json.dumps(self, default=_dump_if_can).encode()

    @classmethod
    def deserialize(cls, bytes_: bytes) -> Self:
        response_s = json.loads(bytes_)
        if isinstance(response_s, list):
            return cls(
                result=[cls.load(response) for response in response_s],
                id=_BATCH,
            )
        return cls.load(response_s)


class Request:
    def __init__(
        self,
        method: str,
        params: list[Any] | tuple[Any, ...] | dict[str, Any] | None = None,
        *,
        id: int | str | None = _MISSING,
    ) -> None:
        self.id = id
        self.params = params
        self.method = method
        self._batch = []

    @classmethod
    def batch(cls, requests: list[Self]) -> Self:
        request = cls(_BATCH, id=_BATCH)
        request._batch = requests
        return request

    def resolve(self, method_lookup: dict[str, Callable]) -> Response | None:
        if self.id is _BATCH:
            results = [
                request.resolve(method_lookup) for request in self._batch
            ]
            filtered = [result for result in results if result]
            response = Response(result=filtered, id=_BATCH)
            return response if filtered else None
        try:
            self._raise_if_cannot_resolve(method_lookup)
            func = method_lookup[self.method]
            if self.params is None:
                res = func()
            elif isinstance(self.params, Sequence):
                res = func(*self.params)
            else:
                res = func(**self.params)
            if self.id is not _MISSING:
                return Response(result=res, id=self.id)
        except Exception as err:
            return self._make_from_exception(err)

    async def resolve_async(
        self, method_lookup: dict[str, Callable[..., Awaitable]]
    ) -> Response | None:
        if self.id is _BATCH:
            results = asyncio.gather(
                *[
                    request.resolve_async(method_lookup)
                    for request in self._batch
                ]
            )
            filtered = [result for result in await results if result]
            response = Response(result=filtered, id=_BATCH)
            return response if filtered else None
        try:
            self._raise_if_cannot_resolve(method_lookup)
            func = method_lookup[self.method]
            if self.params is None:
                res = await func()
            elif isinstance(self.params, Sequence):
                res = await func(*self.params)
            else:
                res = await func(**self.params)
            if self.id is not _MISSING:
                return Response(result=res, id=self.id)
        except Exception as err:
            return self._make_from_exception(err)

    def _raise_if_cannot_resolve(
        self, method_lookup: dict[str, Callable]
    ) -> None:
        if self.id is _PARSE_ERROR:
            raise ParseError
        elif self.id is _INVALID_REQUEST:
            raise InvalidRequestError
        elif self.method not in method_lookup:
            raise MethodNotFoundError

    def _make_from_exception(self, err: Exception) -> Response | None:
        if isinstance(err, ParseError):
            return Response(code=-32700, message='Parse error', id=None)
        elif isinstance(err, InvalidRequestError):
            return Response(code=-32600, message='Invalid Request', id=None)
        elif self.id is _MISSING:
            return
        elif isinstance(err, MethodNotFoundError):
            return Response(
                code=-32601, message='Method not found', id=self.id
            )
        elif isinstance(err, TypeError) and (
            'positional argument' in err.args[0]
            or 'keyword argument' in err.args[0]
        ):
            return Response(
                code=-32602,
                message='Invalid params',
                data=self.get_error_data(err),
                id=self.id,
            )
        else:
            return Response(
                code=-32000,
                message='Server error',
                data=self.get_error_data(err),
                id=self.id,
            )

    @classmethod
    def get_error_data(cls, err: Exception) -> Any:
        return {
            'type': type(err).__name__,
            'info': str(err.args[0]) if err.args else None,
        }

    def dump(self) -> Any:
        if self.id is _BATCH:
            return self._batch
        obj: dict = {
            'jsonrpc': '2.0',
            'method': self.method,
        }
        if self.id is not _MISSING:
            obj['id'] = self.id
        if self.params is not None:
            obj['params'] = self.params
        return obj

    @classmethod
    def load(cls, dict_: dict) -> Self:
        if _validate_schema(dict_, _request_schema):
            dict_ = dict_.copy()
            dict_.pop('jsonrpc')
            return cls(**dict_)
        else:
            return cls(
                _INVALID_REQUEST, (_INVALID_REQUEST,), id=_INVALID_REQUEST
            )

    def serialize(self) -> bytes:
        return json.dumps(self, default=_dump_if_can).encode()

    @classmethod
    def deserialize(cls, bytes_: bytes) -> Self:
        try:
            request_s = json.loads(bytes_)
            if isinstance(request_s, list):
                request = cls(_BATCH, id=_BATCH)
                request._batch = [cls.load(request) for request in request_s]
                return request
            else:
                return cls.load(request_s)
        except json.JSONDecodeError:
            return cls(_PARSE_ERROR, (_PARSE_ERROR,), id=_PARSE_ERROR)
