import functools

import ujson
import asyncio

import aiohttp
from aiohttp import client_exceptions
from tenacity import retry, stop_after_attempt, wait_fixed

from enum import Enum
from types import TracebackType
from typing import Any, Optional, Type, TypeVar

from .tools import Error_Message
from .log import logger, retry_log

T = TypeVar("T")


class HTTPMethod(Enum):
    OPTIONS = "OPTIONS"
    GET = "GET"
    POST = "POST"


class HTTPSession:
    def __init__(self, headers=None):
        self.headers = headers

    async def _create(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            headers=self.headers,
            connector=aiohttp.TCPConnector(ssl=False),
            json_serialize=ujson.dumps,
            timeout=aiohttp.ClientTimeout(total=5 * 60 * 60),
        )

    async def __aenter__(self) -> aiohttp.ClientSession:
        session_object = await self._create()
        self.session = await session_object.__aenter__()
        return self.session

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.session.close()

    def Session(f):
        @functools.wraps(f)
        async def wrapper(
            self,
            *args: Any,
            session: Optional[aiohttp.ClientSession] = None,
            **kwargs: Any,
        ) -> T:
            if session is None:
                async with self._session as session:
                    return await f(self, *args, session=session, **kwargs)
            return await f(self, *args, session=session, **kwargs)

        return wrapper


class HTTPSessionApi:
    host: str
    _session: aiohttp.ClientSession

    def __init__(self, host):
        self.host = host
        self._session = HTTPSession()
        
    async def close_session(self):
        await self._session.session.close()

    # @retry(stop=stop_after_attempt(20), wait=wait_fixed(3), before=retry_log, reraise=True)
    @HTTPSession.Session
    async def __request_data__(
        self,
        method: HTTPMethod,
        path: str,
        *,
        json=None,
        headers=None,
        raise_error=True,
        session: aiohttp.ClientSession = None,
    ) -> T:
        request_url = self.host + path
        try:
            async with session.request(
                method.value,
                request_url,
                headers=headers,
                json=json,
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    raise Error_Message(f"请求错误: {resp.status}")

        except client_exceptions.InvalidURL:
            err_msg = f"错误的服务器地址 ({self.host})"
            if raise_error:
                raise Error_Message(err_msg)
            else:
                logger.warning(err_msg)
        # except client_exceptions.ClientConnectorError:
        #     err_msg = f"无法连接服务器地址 ({self.host})"
        #     if raise_error:
        #         raise Error_Message(err_msg)
        #     else:
        #         logger.warning(err_msg)
        except asyncio.TimeoutError:
            err_msg = f"连接服务器超时 ({self.host})"
            if raise_error:
                raise Error_Message(err_msg)
            else:
                logger.warning(err_msg)
