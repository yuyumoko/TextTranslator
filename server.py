import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.logger import logger as fastapi_logger
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from configparser import ConfigParser
from core import JPTranslator, OpenAiServer

from utils import logger

app = FastAPI()



async def connect_openai_servers():
    server_list_config = ConfigParser()
    server_list_config.read("server-list.ini", encoding="utf-8")

    tg = JPTranslator()
    for config in server_list_config._sections.values():
        if config.get("enable", "").lower() in ["false", "no", "n", "0"]:
            continue

        if await tg.connect_server(OpenAiServer(**config)):
            pass
        else:
            logger.error(f"服务器 [{config['server_name']}] 连接失败")

    await tg.servers_load_default_model(no_log=True)

    tg.start_server()

    if len(tg.servers) == 0:
        logger.error("没有可用的API服务器")
        logger.error("请检查配置文件 server-list.ini 是否正确配置")
        logger.error(
            "如果没有服务器, 请到 https://pan.baidu.com/s/15nk8-pUzDeXW_jgFFvM9Pw?pwd=2z55 下载"
        )
        raise Exception("没有可用的API服务器")

    return tg

# Configure CORS settings to allow all origins, methods, and headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.options("/")
async def options_route():
    return JSONResponse(content="OK")

TG: JPTranslator = None

async def connect_instance():
    global TG
    if TG is None:
        TG = await connect_openai_servers()
    TG.result_data = {}

@app.post("/translateJP")
async def translateJP(request: Request):
    body = await request.json()
    text_list = body.get("text_list")
    if not text_list:
        raise HTTPException(status_code=400, detail="Missing text parameter")

    target_out_file = body.get("target_out_file")
    tran_cache_file = body.get("tran_cache_file")
    is_strictest = body.get("is_strictest", False)
    glossary_path = body.get("glossary_path")
    glossary = body.get("glossary")
    no_save_file = True
    
    await connect_instance()
    
    return JSONResponse(
        await TG.translate(
            text_list,
            target_out_file,
            tran_cache_file,
            is_strictest,
            glossary_path,
            glossary,
            no_save_file,
        )
    )


def run_server(is_public=False, port=7680):
    server_addr = "0.0.0.0" if is_public else "127.0.0.1"
    logger.info(f"Starting server on http://{server_addr}:{port}")
    uvicorn.run(app, host=server_addr, port=port, access_log=False)
