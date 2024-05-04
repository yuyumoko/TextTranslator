import os
import re
import sys
import hashlib
import inspect
import unicodedata

from threading import Thread
from pathlib import Path
from ruamel.yaml import YAML
from tqdm import tqdm

from .simple_config import SimpleConfig


def find_unity_game_data_path(game_path: Path):
    if game_path.suffix == ".exe":
        game_path = game_path.parent

    game_exe = list(
        filter(
            lambda file: file.with_name(file.stem + "_Data").exists(),
            game_path.glob("*.exe"),
        )
    )[0]
    return game_exe.with_name(game_exe.stem + "_Data")


def has_japanese(text):
    text = unicodedata.normalize("NFKC", text)
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4DBF\u4E00-\u9FFF]", text))

def get_japanese_text(text):
    text = unicodedata.normalize("NFKC", text)
    return re.findall(r"[\u3040-\u30ff\u3400-\u4DBF\u4E00-\u9FFF]+", text)

    # japanese_pattern = re.compile(
    #     r"[\u3040-\u309F\u30A0-\u30FA\u30FD-\u30FF\uFF66-\uFF9F]+"
    # )
    # return bool(japanese_pattern.search(text))


def is_repetitive(text):
    # 检查文本是否包含重复的字或句子
    return re.search(r"((.|\n)+?)(?:\1){15,}", text) is not None


def has_chinese(text):
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def read_yaml(file_path: Path):
    file_path = file_path if isinstance(file_path, Path) else Path(file_path)
    with file_path.open(mode="r", encoding="utf-8") as f:
        return dict(YAML(typ="safe", pure=True).load(f))


class Error_Message(Exception):
    def __init__(self, message=""):
        self.message = message

    def __repr__(self):
        return self.message


def get_ecx_path(*paths):
    base_path = Path(sys.argv[0]).resolve().parent
    if (base_path / "_internal").exists():
        base_path = base_path / "_internal"
    return str(base_path.joinpath(*paths))


def md5(context):
    return hashlib.md5(context).hexdigest()


def str2md5(s):
    return md5(str(s).encode())


class Config(SimpleConfig): ...


def filename_filter(filename: str) -> str:
    return re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_", filename)


def get_func_key(func, *fn_args, **fn_kwargs):
    bound = inspect.signature(func).bind(*fn_args, **fn_kwargs)
    bound.apply_defaults()
    bound.arguments.pop("self", None)
    return str2md5(f"{func.__name__}@{bound.arguments}")


def create_thread(func: callable, task_id: str = None, *args, **kwargs):
    if task_id is None:
        task_id = get_func_key(func, *args, **kwargs)
    t = Thread(target=func, args=args, kwargs=kwargs, name=task_id)
    t.setDaemon(True)
    t.start()
    return task_id, t


def size_format(size):
    if size < 1000:
        return "%i" % size + "B"
    elif 1000 <= size < 1000000:
        return "%.1f" % float(size / 1000) + "KB"
    elif 1000000 <= size < 1000000000:
        return "%.1f" % float(size / 1000000) + "MB"
    elif 1000000000 <= size < 1000000000000:
        return "%.1f" % float(size / 1000000000) + "GB"
    elif 1000000000000 <= size:
        return "%.1f" % float(size / 1000000000000) + "TB"


def file_size_str(path):
    return size_format(os.stat(path).st_size)


def search_object_text(
    data,
    filter: callable,
    description=None,
    results=None,
    parent_path="",
    max_depth=None,
):
    if results is None:
        results = []
    if description is None:
        description = "searching for text"

    progress_bar = tqdm(desc=description, total=1)

    def recursive_check(data, results, parent_path):

        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{parent_path}.{key}" if parent_path else key
                
                # skip spine data
                if "skeleton" in current_path:
                    continue
                if data.get("asset_name", "").endswith(".atlas"):
                    continue
                
                if isinstance(value, (str, bytes)):
                    if filter(value):
                        results.append(
                            {
                                "field": key,
                                "text": value,
                                "text_hash": str2md5(value),
                                "parent_path": parent_path,
                                "full_path": current_path,
                            }
                        )
                        continue
                recursive_check(value, results, current_path)
                progress_bar.update(1)
        elif isinstance(data, list):
            for index, item in enumerate(data):
                current_path = f"{parent_path}[{index}]"
                recursive_check(item, results, current_path)
                progress_bar.update(1)
        elif isinstance(data, (str, bytes)):
            if filter(data):
                results.append(
                    {
                        "field": "",
                        "text": data,
                        "text_hash": str2md5(data),
                        "parent_path": parent_path,
                        "full_path": parent_path,
                    }
                )
                progress_bar.update(1)

    recursive_check(data, results, parent_path)
    progress_bar.close()
    return results


def find_object_by_str_path(data, full_path):
    path_components = full_path.lstrip(".").split(".")
    current_obj = data
    for component in path_components:
        if "[" in component and component.endswith("]"):
            list_field, list_index = component.split("[")
            list_index = int(list_index.rstrip("]"))
            current_obj = current_obj[list_field][list_index]
        else:
            current_obj = current_obj[component]
    return current_obj


def update_object_by_str_path(data, full_path, new_value):
    path_components = full_path.lstrip(".").split(".")
    current_obj = data
    for component in path_components[:-1]:
        if "[" in component and component.endswith("]"):
            list_field, list_index = component.split("[")
            list_index = int(list_index.rstrip("]"))
            current_obj = current_obj[list_field][list_index]
        else:
            current_obj = current_obj[component]
    last_field = path_components[-1]
    if "[" in last_field and last_field.endswith("]"):
        list_field, list_index = last_field.split("[")
        list_index = int(list_index.rstrip("]"))
        current_obj[list_field][list_index] = new_value
    else:
        current_obj[last_field] = new_value
