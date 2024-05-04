import UnityPy

from pathlib import Path
from tqdm import tqdm
from UnityPy.classes import Font

from utils import find_unity_game_data_path, logger
from .AssetsTools.AssetsTools import get_all_assets_files

def replace_unity_font(game_path: Path, font_path: Path):
    font_data = list(font_path.read_bytes())
    
    for assets_path in get_all_assets_files(find_unity_game_data_path(game_path)):
        env = UnityPy.load(assets_path)
        is_changed = False
        
        for obj in env.objects:
            if obj.type.name == "Font":
                font : Font = obj.read()
                # if font.m_FontData:
                #     extension = ".ttf"
                #     if font.m_FontData[0:4] == b"OTTO":
                #         extension = ".otf"
                # font.m_FontData = font_data
                logger.info(f"Replace font [{font.name}] ..")
                tree = obj.read_typetree()
                tree["m_FontData"] = font_data
                obj.save_typetree(tree)
                is_changed = True
        
        if is_changed:
            logger.info(f"write file {assets_path}")
            data = env.file.save()
            with open(assets_path, "wb") as f:
                    f.write(data)
    logger.info("Done")