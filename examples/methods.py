import asyncio
import time
from typing import Callable


def sync_sleep(seconds: int) -> str:
    time.sleep(seconds)
    return f'slept for {seconds}s'


def sync_crash_on_call() -> None:
    raise Exception('my call crashed')


def sync_sum_numbers(*args: int) -> int:
    return sum(args)


def sync_say_hello(word: str) -> str:
    return f'hello {word}!'


sync_method_lookup: dict[str, Callable] = {
    'sleep': sync_sleep,
    'crash_on_call': sync_crash_on_call,
    'sum_numbers': sync_sum_numbers,
    'say_hello': sync_say_hello,
}


async def async_sleep(seconds: int) -> str:
    await asyncio.sleep(seconds)
    return f'slept for {seconds}s'


async def async_crash_on_call() -> None:
    return sync_crash_on_call()


async def async_sum_numbers(*args: int) -> int:
    return sync_sum_numbers(*args)


async def async_say_hello(word: str) -> str:
    return sync_say_hello(word)


async_method_lookup: dict[str, Callable] = {
    'sleep': async_sleep,
    'crash_on_call': async_crash_on_call,
    'sum_numbers': async_sum_numbers,
    'say_hello': async_say_hello,
}
