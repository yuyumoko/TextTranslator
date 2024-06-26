import shutil
import UnityPy

from pathlib import Path
from tqdm import tqdm
from UnityPy.classes import Font

from utils import find_unity_game_data_path, logger
from .AssetsTools.AssetsTools import get_all_files, AssetsTools, FileType


from fontTools import subset
from fontTools.ttLib import TTFont

from core.TextGeneration.LocalJsonHandle import LocalJsonHandle
# from .Font_OTF2TTF  import otf_to_ttf


DEFAULT_CHARSET = ".;,:?!\"/<>'()-@#￥$%&*+=。？！，、；：“”‘’「」『』（）[]〔〕【】——……—-～·《》〈〉﹏﹏___. 0 1 2 3 4 5 6 7 8 9 A B C D E F G H I J K L M N O P Q R S T U V W X Y Z a b c d e f g h i j k l m n o p q r s t u v w x y z < > æ"
DEFAULT_CHARSET += "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ[]{}()|~`^@"



def replace_unity_font(game_path: Path, font_path: Path):
    logger.info("make temp font...")
    localJsonHandle = LocalJsonHandle()
    localJsonHandle.set_cache_path(game_path)
    all_text = localJsonHandle.load_prepare_text()
    subset_chars = "".join(frozenset("".join(all_text.values()).replace("\n", "") + DEFAULT_CHARSET))
    temp_font_path = localJsonHandle.out_json_path.parent / "custom_font.ttf"
    make_temp_font(font_path, temp_font_path, subset_chars)
    logger.info(f"make temp font done.")
    
    write_unity_font(game_path, temp_font_path)
    
    
    

def make_temp_font(src_font_path: Path, dist_font_path: Path, subset_chars: str):
    options = subset.Options()
    font = subset.load_font(src_font_path, options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=subset_chars)
    subsetter.subset(font)
    subset.save_font(font, dist_font_path, options)


def write_unity_font(game_path: Path, font_path: Path):
    AT = AssetsTools(find_unity_game_data_path(game_path))
    
    font_data = list(font_path.read_bytes())
    
    asset_files = get_all_files(game_path, False)
    
    for file_type, stream, assets_path in tqdm(asset_files, desc="Loading assets"):
        env = UnityPy.load(assets_path)
        is_changed = False

        for obj in env.objects:
            if obj.type.name == "Font":
                font: Font = obj.read()
                # if font.m_FontData:
                #     extension = ".ttf"
                #     if font.m_FontData[0:4] == b"OTTO":
                #         extension = ".otf"
                # font.m_FontData = font_data
                logger.info(f"Replace font [{font.name}] ..")
                tree = obj.read_typetree()
                
                # game_font_path = font_path.with_name(font.name + extension)
                # with open(game_font_path, "wb") as f:
                #     f.write(bytearray(tree["m_FontData"]))
                
                # merge_font = MergeFont()
                # merge_font.merge([game_font_path, font_path])
                # merge_font_file = game_font_path.with_stem(game_font_path.stem + " merge")
                # merge_font.save(merge_font_file)
                
                tree["m_FontData"] = font_data
                obj.save_typetree(tree)
                is_changed = True

        if is_changed:
            logger.info(f"write file {assets_path}")
            data = env.file.save()
            
            with open(assets_path, "wb") as f:
                f.write(data)
            
            
            if file_type == FileType.BundleFile:
                assets_path = Path(assets_path)
                temp_mod_path = assets_path.with_suffix(".mod")
                assets_path.rename(temp_mod_path)
                
                AT.compresses_asset_bundle(str(temp_mod_path), output_path=str(assets_path))
                
                
            
    logger.info("Done")