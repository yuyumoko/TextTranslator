import ujson as json

from pathlib import Path
from tqdm import tqdm

from utils import logger, find_object_by_str_path, update_object_by_str_path, str2md5
from .TextFinder import TextFinder, write_json


class WriteMonoBehaviour(TextFinder):
    game_path: Path
    game_data_dir: Path
    game_cache_data_dir: Path

    def __init__(self, game_path: Path):
        super().__init__(game_path)

    def write_cache_to_file(self):
        script_obj_file = self.game_cache_data_dir / "script_obj.json"
        text_data_file = self.game_cache_data_dir / "text_data.json"
        prepare_text_file = self.game_cache_data_dir / "prepare_text.json"

        logger.info("loading cache data")

        with open(script_obj_file, "r", encoding="utf-8") as f:
            script_obj = json.load(f)
        with open(text_data_file, "r", encoding="utf-8") as f:
            text_data: list[dict] = json.load(f)
        with open(prepare_text_file, "r", encoding="utf-8") as f:
            prepare_text_data = json.load(f)

        update_script_obj = []

        with tqdm(total=len(prepare_text_data), desc="update script object") as pbar:
            for prepare_text, prepare_text_value in prepare_text_data.items():
                pbar.update(1)
                if prepare_text_value == "":
                    logger.warning(f"text [{prepare_text}] no value, skip")
                    continue

                prepare_text_hash = str2md5(prepare_text)
                value_hash = str2md5(prepare_text_value)

                for text_data_item in text_data:
                    if text_data_item["text_hash"] != prepare_text_hash:
                        if text_data_item.get("value_hash", "") != value_hash:
                            continue

                    parent_path = text_data_item["parent_path"].split(".")[0]
                    script_obj_info = find_object_by_str_path(script_obj, parent_path)

                    text_data_item["value"] = prepare_text_value
                    text_data_item["value_hash"] = value_hash

                    update_monobehaviour_data = text_data_item.copy()
                    update_monobehaviour_data["info"] = script_obj_info

                    update_script_obj.append(update_monobehaviour_data)

        write_json(self.game_cache_data_dir / "text_data.json", text_data)
        # logger.info("writing script object to file")
        self.at.update_monobehaviour(update_script_obj)
