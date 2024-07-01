from pathlib import Path
import ujson as json

from tqdm import tqdm

from UnityPy.export.Texture2DConverter import parse_image_data, TF
from UnityPy.enums.BuildTarget import BuildTarget

from utils import logger, find_unity_game_data_path, search_object_text, has_japanese

from .AssetsTools.AssetsTools import AssetsTools, get_all_files, FileType
from .AssetsTools.AssetClassID import AssetClassID


def write_json(file_path, data, ensure_ascii=False, indent=4):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)


def read_json(file_path):
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


class TextFinder:
    game_path: Path
    game_data_dir: Path
    game_cache_data_dir: Path

    at: AssetsTools

    script_obj: dict

    def __init__(self, game_path: Path):

        self.game_path = game_path
        self.game_data_dir = find_unity_game_data_path(game_path)

        self.game_cache_data_dir = self.game_data_dir.parent / "Cache"
        self.game_cache_data_dir.mkdir(exist_ok=True)

        self.at = AssetsTools(self.game_data_dir)

    def load_assets_script_obj(self, use_cache=False):
        cache_script_file = self.game_cache_data_dir / "script_obj.json"
        if cache_script_file.exists() and use_cache:
            logger.info("Loading cached script object")
            with open(cache_script_file, "r", encoding="utf-8") as f:
                script_obj = json.load(f)
            self.script_obj = script_obj
            return

        asset_files = get_all_files(self.game_data_dir.parent)
        logger.info("Loading resources..")
        if self.at.load_resources() is False:
            logger.warn("resources not loaded, container is empty")

        for file_type, stream, file in tqdm(asset_files, desc="Loading assets"):
            if file_type == FileType.AssetsFile:
                self.at.load_asset(file, stream)
            elif file_type == FileType.BundleFile:
                self.at.load_asset_bundle(file, stream)

        pbar = tqdm(total=len(self.at.assets))

        def process_assets(total_info_num):
            pbar.update()
            pbar.set_description(f"dumping {total_info_num} fields")

        script_obj = self.at.dump_monobehaviour(True, process_assets)

        # with open(cache_script_file, "w", encoding="utf-8") as f:
        #     json.dump(script_obj, f, ensure_ascii=False)
        write_json(cache_script_file, script_obj, indent=0)

        self.script_obj = script_obj

    def dump_prepare_text(self):
        self.load_assets_script_obj()
        text_data = search_object_text(self.script_obj, has_japanese)
        prepare_json_data = read_json(self.game_cache_data_dir / "prepare_text.json")

        for data in text_data:
            value = prepare_json_data.get(data["text"], "")
            prepare_json_data[data["text"]] = value

        write_json(self.game_cache_data_dir / "text_data.json", text_data)

        write_json(self.game_cache_data_dir / "prepare_text.json", prepare_json_data)

        if not (self.game_cache_data_dir / "prompt_text.json").exists():
            write_json(self.game_cache_data_dir / "prompt_text.json", {})

        logger.info("done, prepare_text.json and text_data.json are generated")

    def replace_font(self, font_path: Path):

        font_data = font_path.read_bytes()

        asset_files = get_all_files(self.game_data_dir.parent)
        logger.info("Loading resources..")
        if self.at.load_resources() is False:
            logger.warn("resources not loaded, container is empty")

        for file_type, stream, file in tqdm(asset_files, desc="Loading assets"):
            if file_type == FileType.AssetsFile:
                self.at.load_asset(file, stream)
            elif file_type == FileType.BundleFile:
                self.at.load_asset_bundle(file, stream)

        afileInstCache = {}

        with tqdm(total=len(self.at.assets)) as pbar:
            for asset_info in self.at.assets.values():
                file_inst = asset_info.file_inst
                pbar.update()

                for goInfo in self.at.filter_type(
                    file_inst, AssetClassID.MonoBehaviour
                ):

                    try:
                        goBase = self.at.manager.GetBaseField(file_inst, goInfo)
                    except Exception as e:
                        logger.error(
                            f"field load:{asset_info.file_path} PathId:[{goInfo.PathId}] Source:{e.Source} Message:{e.Message}"
                        )
                        continue

                    # bytes(goBase.WriteToByteArray())

                    name = goBase["m_Name"].AsString

                    components = goBase["m_Component.Array"]

                    if "SDF" in name:
                        name
                        # type_name = goBase.TypeName
                        # asset_name = self.at.AT.AssetHelper.GetAssetNameFast(file_inst.file, self.at.manager.ClassDatabase, goInfo)
                        
                        
                        scriptBaseField = self.at.manager.GetExtAsset(file_inst, goBase["m_Script"]).baseField
                        class_name = scriptBaseField["m_Name"].AsString # ' '
                        SDFBehaviour = self.at.dump_children(goBase)
                        
                        atlas_path_id = SDFBehaviour['atlas']['m_PathID']
                        
                        # material_path_id = SDFBehaviour['material']['m_PathID']
                        # material_goInfo = file_inst.file.GetAssetInfo(material_path_id)
                        # material_goBase = self.at.manager.GetBaseField(file_inst, material_goInfo)
                        # material = self.at.dump_children(material_goBase)
                        
                        # atlas_path_id = material['m_SavedProperties']['m_TexEnvs'][0]['second']['m_Texture']['m_PathID']
                        atlas_goInfo = file_inst.file.GetAssetInfo(atlas_path_id)
                        atlas_goBase = self.at.manager.GetBaseField(file_inst, atlas_goInfo)
                        
                        texture = self.at.Texture.TextureFile.ReadTextureFile(atlas_goBase)
                        # textureBgraRaw = texture.GetTextureData(file_inst)
                        
                        if texture.pictureData.Length == 0 and texture.m_StreamData.size != 0:
                            fixedStreamPath = texture.m_StreamData.path
                            
                            bundle = file_inst.parentBundle.file
                            reader = bundle.DataReader
                            # resourceFileIndex = bundle.GetFileIndex(fixedStreamPath.split("/")[-1])
                            # resourceFileOffset, resourceFileLength = bundle.GetFileRange(resourceFileIndex, resourceFileOffset, resourceFileLength)
                            
                            # pictureData = bytearray(texture.m_StreamData.size)
                            # bundle.Reader.Position = resourceFileOffset + texture.m_StreamData.offset
                            # bundle.Reader.Read(pictureData, 0, len(pictureData))
                            # pictureData = bundle.Reader.ReadBytes(texture.m_StreamData.size)
                            
                            info = self.at.AT.BundleHelper.GetDirInfo(file_inst.parentBundle.file, fixedStreamPath.split("/")[-1])
                            reader.Position = info.Offset + texture.m_StreamData.offset
                            pictureData = reader.ReadBytes(texture.m_StreamData.size)
                            
                            m_TextureFormat = self.at.Texture.TextureFormat(texture.m_TextureFormat)
                            m_Width = texture.m_Width
                            m_Height = texture.m_Height
                            
                            img = parse_image_data(pictureData, m_Width, m_Height, TF(texture.m_TextureFormat), None, BuildTarget.UnknownPlatform, flip=True)
                            img.save(str(self.game_cache_data_dir / f"{name}.png"))
                            # textureBgraRaw = texture.DecodeManaged(pictureData, m_TextureFormat, m_Width, m_Height, True)
                        
                        
                        

                    for data in components:
                        # componentPointer = data["component"]
                        # componentExtInfo = self.at.manager.GetExtAsset(file_inst, componentPointer)
                        # componentType = AssetClassID(componentExtInfo.info.TypeId)

                        field_name = data.FieldName
                        print(f"{name} {field_name}")

                        if field_name == "m_GlyphTable":
                            field_name

        #         for goInfo in FontBaseList:
        #             goBase = self.at.manager.GetBaseField(file_inst, goInfo)
        #             font_name = goBase["m_Name"].AsString
        #             pbar.set_description(f"Replacing font {font_name}")

        #             newBaseField = self.at.manager.CreateValueBaseField(
        #                 file_inst, AssetClassID.Font.value
        #             )
        #             newBaseField["m_FontData"].AsByteArray = font_data

        #             newBaseField["m_Name"].AsString = font_name
        #             newInfo = self.at._AT.AssetFileInfo.Create(
        #                 file_inst.file, goInfo.PathId, AssetClassID.Font.value
        #             )
        #             newInfo.SetNewData(newBaseField)

        #             file_inst.file.Metadata.RemoveAssetInfo(goInfo)
        #             file_inst.file.Metadata.AddAssetInfo(newInfo)

        #             if afileInstCache.get(file_inst.path) is None:
        #                 afileInstCache[file_inst.path] = file_inst

        # for afileInst in afileInstCache.values():
        #     self.at.save_assets(afileInst)
