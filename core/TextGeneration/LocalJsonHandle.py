import ujson as json

from pathlib import Path
from utils import logger, find_unity_game_data_path


def read_json(file_path: Path):
    if not file_path.exists():
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


class LocalJsonHandle:
    prepare_data = None
    out_json_name = "prepare_text.json"
    out_json_path = None

    def set_cache_path(self, cache_path: Path):
        if cache_path.suffix == ".exe":
            self.cache_path = cache_path.parent
        else:
            self.cache_path = cache_path
        
        prepare_text_path = self.cache_path / self.out_json_name
        if not prepare_text_path.exists():
            prepare_text_path = self.cache_path / "Cache" / self.out_json_name
            if not prepare_text_path.exists():
                raise FileNotFoundError(
                    f"{prepare_text_path} not exists, please generate it first."
                )
                
        self.out_json_path = prepare_text_path
        self.cache_path = prepare_text_path.parent

    def load_prepare_text(self, target_file: Path = None):
        if target_file is None:
            target_file = self.cache_path / self.out_json_name
        
        return read_json(target_file)

    def read_prompt_text(self):
        return read_json(self.cache_path / "prompt_text.json")

    def read_prepare_text(self, target_file: Path = None):
        prepare_data = self.load_prepare_text(target_file)
        return [k for k, v in prepare_data.items() if v == ""]

    def save_prepare_text(self, data: dict, target_file: Path = None):
        if target_file is None:
            target_file = self.cache_path / self.out_json_name
        
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def update_prepare_text(self, key: str, value: str, target_file: Path = None)   :
        if self.prepare_data is None:
            self.prepare_data = self.load_prepare_text(target_file)
        if self.prepare_data is None:
            return
        self.prepare_data[key] = value
        self.save_prepare_text(self.prepare_data, target_file)
