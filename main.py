import os
import asyncio
import ujson as json

from menu_tools import MenuTools

from pathlib import Path

from tqdm import tqdm

from utils import logger, get_ecx_path, has_japanese
from utils.arg_require import ArgRequire, ArgRequireOption


__version__ = "0.6.7s"

ag = ArgRequire(ArgRequireOption(save=True, save_path="config.ini"))


last_game_path = None


async def connect_openai_servers():
    from configparser import ConfigParser
    from core import JPTranslator, OpenAiServer

    server_list_config = ConfigParser()
    server_list_config.read("server-list.ini", encoding="utf-8")

    tg = JPTranslator()
    for config in server_list_config._sections.values():
        if config.get("enable", "").lower() in ["false", "no", "n", "0"]:
            continue

        logger.info(f"连接API服务器[{config['server_name']}]: {config['api_url']}")
        if await tg.connect_server(OpenAiServer(**config)):
            logger.info(f"服务器 [{config['server_name']}] 连接成功")
        else:
            logger.error(f"服务器 [{config['server_name']}] 连接失败")

    await tg.servers_load_default_model()

    tg.start_server()

    if len(tg.servers) == 0:
        logger.error("没有可用的API服务器")
        logger.error("请检查配置文件 server-list.ini 是否正确配置")
        logger.error(
            "如果没有服务器, 请到 https://pan.baidu.com/s/15nk8-pUzDeXW_jgFFvM9Pw?pwd=2z55 下载"
        )
        return

    return tg


@ag.apply("请拖入游戏目录")
def unity_game(game_path: Path):
    from core.UnityExtractor.TextFinder import TextFinder

    global last_game_path

    utf = TextFinder(game_path)
    utf.dump_prepare_text()

    last_game_path = utf.game_path


async def run_translate_async(game_path: Path):
    tg = await connect_openai_servers()

    tg.set_cache_path(game_path)
    text_list = tg.read_prepare_text()

    await tg.translate(text_list)

    # await tg.unload_model()
    logger.info("翻译完成")


@ag.apply("请拖入游戏目录")
def run_translate(game_path: Path):
    asyncio.run(run_translate_async(game_path))


@ag.apply("请拖入游戏目录")
def run_write_unity_file(game_path: Path):
    from core.UnityExtractor.WriteMonoBehaviour import WriteMonoBehaviour

    wmb = WriteMonoBehaviour(game_path)
    wmb.write_cache_to_file()


@ag.apply("请拖入游戏目录")
def run_replace_font(game_path: Path):
    from core.UnityExtractor.ReplaceFont import replace_unity_font

    # ./font/unifont-all.ttf
    replace_unity_font(game_path, Path("./font/unifont-all.ttf"))
    # replace_unity_font(game_path, [
    #     Path("./font/unifont-all.ttf"),
    #     Path("./font/NotoSansSC-Regular.otf"),
    # ])

    # from core.UnityExtractor.TextFinder import TextFinder

    # custom_font_path = Path("./font/NotoSansSC-Regular.otf")
    # if not custom_font_path.exists():
    #     logger.error("字体文件不存在")
    #     return

    # utf = TextFinder(game_path)
    # utf.replace_font(custom_font_path)


async def run_translate_json_async(json_path: Path):
    pending_file = json_path.with_stem(json_path.stem + "_Translated_Cache")
    tran_cache = json_path.with_stem(json_path.stem + "_Translated")

    if not pending_file.exists():
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if tran_cache.exists():
            with tran_cache.open("r", encoding="utf-8") as f:
                cache_data = json.load(f)
        else:
            cache_data = {}

        pending_data = {}
        for key, value in tqdm(data.items(), desc="生成待翻译文件"):
            if has_japanese(key):
                pending_data[key] = cache_data.get(key, "")
            else:
                pending_data[key] = value

        with pending_file.open("w", encoding="utf-8") as f:
            json.dump(pending_data, f, ensure_ascii=False, indent=4)

    tg = await connect_openai_servers()
    tg.cache_path = tran_cache.parent
    text_list = tg.read_prepare_text(pending_file)

    await tg.translate(
        text_list, target_out_file=pending_file, tran_cache_file=tran_cache
    )
    logger.info("翻译完成")


@ag.apply("请拖入其他需要翻译的Json文件")
def run_translate_json(json_path: Path):
    asyncio.run(run_translate_json_async(json_path))


def run():
    MenuTools(
        title=f"--- 简简单单翻译一下  v{__version__} ---",
        options={
            unity_game: "1. 提取游戏文本资源 (先选这个, 生成需要翻译的文本)",
            run_translate: "2. 使用AI翻提取前的文本",
            run_write_unity_file: "3. 替换游戏内文本 (翻译完成后, 选这个)",
            run_replace_font: "4. 替换游戏内字体 (出现口口或者识别不出中文的情况, 选这个)",
            run_translate_json: "额外功能: 翻译其他工具导出的Json文件",
        },
        args={
            run_translate: {"game_path": last_game_path},
            run_write_unity_file: {"game_path": last_game_path},
            run_replace_font: {"game_path": last_game_path},
        },
    ).show()
    os.system("pause")
    run()


if __name__ == "__main__":
    run()
