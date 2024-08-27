# Copyright 2024 The habitat Authors. All rights reserved.
# Licensed under the Apache License Version 2.0 that can be found in the
# LICENSE file in the root directory of this source tree.

import asyncio
import functools
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from urllib import request
from urllib.parse import urlparse

import aiohttp
import asyncio_atexit
from aiohttp.web_exceptions import HTTPError

from core.common.http_status import client_error, server_error, success
from core.settings import DEBUG

DEFAULT_TIMEOUT = 20
MAX_CONCURRENCY = int(os.environ.get('HABITAT_CONCURRENCY', 500))


async def close_session(session):
    if not session.closed:
        logging.debug(f'closing session {session}')
        await session.close()


async def on_request_start(session, context, params):
    logging.getLogger('aiohttp.client').debug(f'Starting request <{params}>')


async def on_request_end(session, context, params):
    logging.getLogger('aiohttp.client').debug(f'End request <{params}>')


class HttpClient:

    def __init__(self, base_url=None, headers=None, executors=50, thread_pool=None):
        self._thread_pool = thread_pool or ThreadPoolExecutor(executors)
        parsed_url = urlparse(base_url)
        self._base_url = f'{parsed_url.scheme}://{parsed_url.netloc}'
        self._headers = headers or {}
        self._base_path = parsed_url.path
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        client_timeout = aiohttp.ClientTimeout(sock_connect=10, sock_read=DEFAULT_TIMEOUT)

        trace_configs = []
        if DEBUG:
            logging.basicConfig(level=logging.DEBUG)
            trace_config = aiohttp.TraceConfig()
            trace_config.on_request_start.append(on_request_start)
            trace_config.on_request_end.append(on_request_end)
            trace_configs.append(trace_config)

        self._session = aiohttp.ClientSession(
            base_url=self._base_url, timeout=client_timeout, trace_configs=trace_configs)
        asyncio_atexit.register(functools.partial(close_session, self._session))

    async def async_request(
        self, method, path, payload=None, timeout=DEFAULT_TIMEOUT, extra_headers=None, json=False, retry=0,
        raise_on_client_error=True, **kwargs
    ):
        """
        send a http request asynchronously
        @param raise_on_client_error:
        @param retry:
        @param kwargs:
        @param json:
        @param method:
        @param path:
        @param payload:
        @param timeout:
        @param extra_headers:
        @return: (response instance, headers, data)
        """
        path = f'{self._base_path}{"" if path.startswith("/") else "/"}{path}'
        logging.debug(f'send async request method: {method} base_url: {self._base_url} '
                      f'path: {path} extra headers: {extra_headers}')

        client_timeout = aiohttp.ClientTimeout(sock_connect=10, sock_read=timeout)

        remained_changes = retry + 1
        async with self._semaphore:
            while remained_changes > 0:
                remained_changes -= 1
                try:
                    async with self._session.request(
                        url=path,
                        data=payload, method=method, headers={**self._headers, **(extra_headers or {})},
                        timeout=client_timeout,
                        **kwargs
                    ) as resp:
                        if server_error(resp.status) or (client_error(resp.status) and raise_on_client_error):
                            raise HTTPError(reason=resp.reason, headers=resp.headers)

                        if not success(resp.status):
                            return resp, resp.headers, None

                        if json:
                            data = await resp.json()
                        else:
                            data = await resp.read()
                        logging.debug(
                            f'response of async request to {path}: status: {resp.status} headers: {resp.headers}'
                        )
                        return resp, resp.headers, data
                except Exception as e:
                    if remained_changes > 0:
                        logging.warning(f'got an exception: \"{e}\", retry')
                        continue
                    else:
                        logging.warning(
                            f'got an exception when sending async request {method}, base_url: {self._base_url} '
                            f'path: {path} extra headers: {extra_headers} status: {resp.status} headers: {resp.headers}'
                        )
                        raise e

    def request(self, method, path, payload=None, timeout=DEFAULT_TIMEOUT, extra_headers=None):
        full_url = f'{self._base_url}{self._base_path}{"" if path.startswith("?") else "/"}{path}'
        logging.debug(f'send request method: {method} url: {full_url} extra headers: {extra_headers}')
        req = request.Request(
            full_url,
            data=payload, method=method, headers={**self._headers, **(extra_headers or {})}
        )
        try:
            resp = request.urlopen(req, timeout=timeout)
        except Exception as e:
            logging.warning(f'got an exception during sending request {method} to {full_url}, req: {req}')
            raise e

        try:
            content = resp.read()
        except Exception as e:
            logging.debug('got an exception when trying to read the response.')
            raise e

        logging.debug(f'response of request to {full_url}: status: {resp.status} content: {content}')
        return resp, content
