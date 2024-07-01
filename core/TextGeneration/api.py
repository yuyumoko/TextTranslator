import asyncio
from aiohttp import client_exceptions
from queue import Queue
from threading import Thread, Lock

from typing import Any, TypeVar, List, Dict
from pydantic import BaseModel, FilePath


from collections import namedtuple

from .typing import ChatCompletionRequest, CurrentModelInfo
from utils.session import HTTPMethod, HTTPSessionApi

from utils import logger, read_yaml, str2md5, has_japanese, japanese_normalize

T = TypeVar("T")

API = {
    "state": {"method": HTTPMethod.OPTIONS, "path": "/"},
    "token": {"method": HTTPMethod.POST, "path": "/api/token"},
    "openai_completions": {
        "method": HTTPMethod.POST,
        "path": "/v1/completions",
    },
    "openai_chat_completions": {
        "method": HTTPMethod.POST,
        "path": "/v1/chat/completions",
    },
    "current_model_info": {
        "method": HTTPMethod.GET,
        "path": "/v1/internal/model/info",
    },
    "model_list": {
        "method": HTTPMethod.GET,
        "path": "/v1/internal/model/list",
    },
    "load_model": {
        "method": HTTPMethod.POST,
        "path": "/v1/internal/model/load",
    },
    "unload_model": {
        "method": HTTPMethod.POST,
        "path": "/v1/internal/model/unload",
    },
}

API_PARAMS = namedtuple("API_PARAMS", "method, path")

OPENKEY_STATE = namedtuple("OPENKEY_STATE", "Status, Total, Used, Remaining")
OPENKEY_STATE_ERROR = namedtuple("OPENKEY_STATE_ERROR", "Status, Error")


class TextGenerationAPI(HTTPSessionApi):
    model_config: dict
    api_key: str
    server_type: str = "default"
    openkey_state: OPENKEY_STATE | OPENKEY_STATE_ERROR = None
    model_name: str = None

    def __init__(
        self,
        api_url: str,
        api_key: str,
        server_type: str,
        model_config: dict = None,
        model_name: str = None,
        http_proxy: str = None,
    ):
        self.api_key = api_key
        self.server_type = server_type
        self.model_name = model_name
        super().__init__(api_url, http_proxy)
        self.model_config = model_config or {}

    async def request(self, api: API_PARAMS, raise_error=True, **kwargs) -> Any:
        api = api if isinstance(api, API_PARAMS) else API_PARAMS(**api)
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return await self.__request_data__(
            api.method, api.path, headers=headers, raise_error=raise_error, **kwargs
        )

    async def get_openkey_state(self) -> OPENKEY_STATE | OPENKEY_STATE_ERROR:
        res = await self.request(
            API["token"],
            host="https://billing.openkey.cloud",
            json={"api_key": self.api_key},
        )
        if res["Status"] == 1:
            self.openkey_state = OPENKEY_STATE(**res)
        else:
            self.openkey_state = OPENKEY_STATE_ERROR(**res)
        return self.openkey_state

    async def state(self) -> bool:
        try:
            if self.server_type == "openkey":
                res = await self.get_openkey_state()
                return res.Status == 1
            elif self.server_type == "openai":
                return True
            else:
                res = await self.request(API["state"])
                return res == "OK"
        except Exception as e:
            return False

    async def has_load_model(self, model_name: str = None) -> bool:
        server_state = await self.state()
        if not server_state:
            return False

        model_info = await self.current_model_info()
        if model_info.model_name == "None" and model_name is None:
            return False

        if model_name and model_info.model_name != model_name:
            return False

        return True

    async def load_one_model(self) -> bool:
        model_list = await self.get_model_list()
        if len(model_list) == 0:
            logger.warn("No models loaded")
            return False
        logger.info("[%s] load model [%s] ..." % (self.host, model_list[0]))
        await self.load_model(model_list[0])
        # logger.info("Loaded default model.")
        return True

    async def openai_completions(self, params: ChatCompletionRequest) -> Any:
        res = await self.request(API["openai_completions"], json=params)
        return res["choices"][0]["text"].strip()

    async def openai_chat_completions(self, params: ChatCompletionRequest) -> Any:
        res = await self.request(API["openai_chat_completions"], json=params)
        return res["choices"][0]["message"]["content"].strip()

    async def current_model_info(self) -> CurrentModelInfo:
        res = await self.request(API["current_model_info"])
        return CurrentModelInfo(**res)

    async def get_model_list(self) -> list[str]:
        res = await self.request(API["model_list"])
        return res["model_names"]

    async def load_model(self, model_name: str, args: dict = None) -> Any:
        if args is None:
            args = {}

        config = self.model_config.get(model_name + "$", {})
        args.update(config)
        load_params = {"model_name": model_name, "args": args}
        res = await self.request(API["load_model"], json=load_params)
        return res == "OK"

    async def unload_model(self):
        await self.request(API["unload_model"])


class OpenAiServer(BaseModel):
    enable: bool = True
    server_name: str
    api_url: str
    api_key: str
    model_config_path: FilePath = None
    description: str = ""

    server_type: str = "default"
    model_name: str = "default"

    http_proxy: str = None


class QueueServers(BaseModel):
    api: TextGenerationAPI
    config: OpenAiServer

    class Config:
        arbitrary_types_allowed = True


class QueueTextGenerationAPI:
    servers: List[QueueServers] = []
    queue: Queue
    result_lock: Lock
    result_data: Dict[str, str] = {}

    def __init__(self):
        self.queue = Queue()
        self.result_lock = Lock()

    async def connect_server(self, server: OpenAiServer) -> QueueServers:
        model_config = None
        if server.model_config_path is not None:
            model_config = read_yaml(server.model_config_path)

        api = TextGenerationAPI(
            server.api_url,
            server.api_key,
            server.server_type,
            model_config,
            server.model_name,
            server.http_proxy,
        )
        if not await api.state():
            return None
        qs = QueueServers(api=api, config=server)
        self.servers.append(qs)
        return qs

    def start_server(self, server: OpenAiServer = None):
        servers = [server] if server else self.servers
        for s in servers:
            t = Thread(target=self.run_async_server, args=(s,), daemon=True)
            t.start()

    def run_async_server(self, server: QueueServers):
        asyncio.run(self.run_server(server))

    @staticmethod
    def make_chat_completions_content(
        content: str, gpt_prompt_list: List[str] = None
    ) -> str:
        content = "\n".join(content) if isinstance(content, list) else content

        pre_content = "你是一个轻小说翻译模型，可以流畅通顺地以日本轻小说的风格将日文翻译成简体中文，注意不要擅自添加原文中没有的代词，也不要擅自增加或减少换行。\n"
        if gpt_prompt_list is not None and len(gpt_prompt_list) > 0:
            prompt = []
            for gpt_prompt in gpt_prompt_list:
                src = gpt_prompt["src"]
                dst = gpt_prompt["dst"]
                info = gpt_prompt.get("info", "")
                if info:
                    prompt.append(f"{src}->{dst} #{info}")
                else:
                    prompt.append(f"{src}->{dst}")

            gpt_prompt_str = "\n".join(prompt)
            user_prompt = f"根据以下术语表：\n{gpt_prompt_str}\n将下面的日文文本根据上述术语表的对应关系和注释翻译成中文：{content}"
        else:
            user_prompt = f"将下面的日文文本翻译成中文：{content}"

        return {"role": "user", "content": pre_content + user_prompt}

    async def run_server(self, server: QueueServers):
        while True:
            make_content, text, gpt_prompt_list, is_strictest = self.queue.get()
            text_hash = str2md5(text)
            try:
                if text_hash in self.result_data:
                    logger.info(f"{self.queue.qsize()} [{text}] already generated.")
                    continue

                if self.queue.qsize() == 0 and server.api.server_type != "default" and len(self.servers) > 1:
                    self.queue.put((make_content, text, gpt_prompt_list, is_strictest))
                    continue

                # logger.info(f"{self.queue.qsize()} [{server.config.server_name}] -: {text}")

                base_payload = {
                    "stream": False,
                    "max_tokens": 512,
                    "temperature": 0.1,
                    "top_p": 0.3,
                    "frequency_penalty": 0.05,
                }

                if server.api.server_type != "default":
                    payload = {
                        "model": server.api.model_name,
                        "messages": [
                            QueueTextGenerationAPI.make_chat_completions_content(
                                japanese_normalize(text), gpt_prompt_list
                            )
                        ],
                    }
                    payload.update(base_payload)

                    res_text: str = await server.api.openai_chat_completions(payload)
                    if text == res_text:
                        self.queue.put(
                            (make_content, text, gpt_prompt_list, is_strictest)
                        )
                        continue

                    res_text_split = res_text.split("\n")
                    if len(res_text_split) > 1:
                        res_text = res_text_split[-1]

                    res_text = res_text.replace("“", "").replace("”", "")
                else:
                    payload = {
                        "prompt": make_content(
                            japanese_normalize(text), gpt_prompt_list
                        ),
                        "top_k": 40,
                        "repetition_penalty": 1,
                        "do_sample": True,
                        "num_beams": 1,
                    }
                    payload.update(base_payload)
                    res_text: str = await server.api.openai_completions(payload)

                if is_strictest:
                    for end in ["。", "？", "！", "，", "—", "…"]:
                        if res_text.endswith(end):
                            res_text = res_text.rstrip(end)
                            break

                if not text.endswith("。") and res_text.endswith("。"):
                    res_text = res_text.rstrip("。")

                with self.result_lock:
                    if len(res_text) > 500:
                        res_text = res_text[: len(text)]
                        text_list = list(text)
                        text_list.reverse()
                        text_end = []
                        for char in text_list:
                            if not has_japanese(char):
                                text_end.append(char)
                            else:
                                break
                        text_end.reverse()
                        res_text += "".join(text_end)

                    self.result_data[text_hash] = res_text
                    # logger.info(f"[{server.config.server_name}] +: {res_text}")
                    # fmt: off
                    logger.info(f"{self.queue.qsize()} \033[0m(\033[36m{server.config.server_name}\033[0m) [ \033[0;33m{text}\033[0m ] -> [ \033[35m{res_text}\033[0m ]")
                    # fmt: on

            except client_exceptions.ClientConnectorError:
                break
            except Exception as e:
                logger.error(f"Error in server {server.config.server_name}: {e}")
                break
            finally:
                self.queue.task_done()

        logger.error(f"Server [{server.config.server_name}] is disconnected.")

        await server.api.close_session()
        self.servers.remove(server)
        logger.warn(f"[{text}] put back to queue.")
        self.queue.put((make_content, text, gpt_prompt_list, is_strictest))
        await self.wait_server_reconnect(server.config)

    async def wait_server_reconnect(self, openai_config: OpenAiServer):
        while True:
            try:
                if qs := await self.connect_server(openai_config):
                    await self.servers_load_default_model(qs)

                    self.start_server(qs)
                    logger.info(f"Server [{openai_config.server_name}] is reconnected.")
                    break

            except client_exceptions.ClientConnectorError:
                pass
            except Exception as e:
                logger.error(f"Error in server [{openai_config.server_name}]: {e}")

            # logger.warn(f"Wait for server [{openai_config.server_name}] to reconnect...")
            await asyncio.sleep(5)

    async def servers_load_default_model(
        self, server: OpenAiServer = None, no_log=False
    ):
        servers = [server] if server else self.servers

        async def load_default_model(server: QueueServers):
            if server.api.server_type == "openkey":
                if not no_log:
                    logger.info(
                        f"Server [{server.config.server_name}] connected. Used [{server.api.openkey_state.Used}/{server.api.openkey_state.Total}]"
                    )
                return
            if server.api.server_type != "default":
                if not no_log:
                    logger.info(f"Server [{server.config.server_name}] connected.")
                return

            if not await server.api.has_load_model():
                await server.api.load_one_model()
            if not no_log:
                logger.info(
                    f"Success load default model for server {server.config.server_name}"
                )

        cor = [load_default_model(server) for server in servers]
        await asyncio.gather(*cor)
