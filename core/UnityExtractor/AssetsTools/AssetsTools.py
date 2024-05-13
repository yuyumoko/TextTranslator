import os
import sys
import ujson as json

import clr

from enum import IntEnum
from pathlib import Path
from collections import namedtuple, defaultdict

from tqdm import tqdm

from utils import logger, get_ecx_path

from .AssetClassID import AssetClassID

CS_RUNTIME_DIR = get_ecx_path("runtime")


class FileType(IntEnum):
    AssetsFile = 0
    BundleFile = 1
    WebFile = 2
    ResourceFile = 9
    ZIP = 10


Cpp2IL_RUNTIME_DIR = os.path.join(CS_RUNTIME_DIR, "Cpp2IL")
MonoCecil_RUNTIME_DIR = os.path.join(CS_RUNTIME_DIR, "MonoCecil")

CLASSDATATPK_DIR = os.path.join(CS_RUNTIME_DIR, "classdata.tpk")

Path_str = lambda p: str(p.resolve()) if isinstance(p, Path) else p

from UnityPy.helpers.ImportHelper import check_file_type


def get_all_assets_files(data_dir: Path):
    files = []

    def add_if_exists(file):
        file_path = data_dir / file
        if file_path.exists():
            files.append(Path_str(file_path))
            return True
        return False

    add_if_exists("globalgamemanagers")
    add_if_exists("globalgamemanagers.assets")
    add_if_exists("resources.assets")
    idx = 0
    while add_if_exists(f"level{idx}"):
        idx += 1
    idx = 0
    while add_if_exists(f"sharedassets{idx}.assets"):
        idx += 1
    # check_file_type(files[0])
    return files


EXCLUDE_SUFFIX = [
    ".resS",
    ".resource",
    ".config",
    ".xml",
    ".dat",
    ".info",
    ".dll",
    ".json",
]


# from System.IO import MemoryStream
from System.IO import File


def get_all_files(directory: str | Path):
    directory = directory if isinstance(directory, Path) else Path(directory)
    for file in directory.rglob("*"):
        if file.is_file() and file.suffix not in EXCLUDE_SUFFIX:
            file_type, reader = check_file_type(file.open("rb"))
            if file_type == FileType.AssetsFile or file_type == FileType.BundleFile:
                yield file_type, File.OpenRead(str(file)), str(file.resolve())


def pythonnet_init(is_MonoCecil=False):
    if is_MonoCecil:
        sys.path.append(MonoCecil_RUNTIME_DIR)
    else:
        sys.path.append(Cpp2IL_RUNTIME_DIR)

    # import clr
    clr.AddReference("AssetsTools.NET")
    Cpp2IL = None

    if is_MonoCecil:
        clr.AddReference("AssetsTools.NET.MonoCecil")
    else:
        clr.AddReference("AssetsTools.NET.Cpp2IL")
        import AssetsTools.NET.Cpp2IL as Cpp2IL

    import AssetsTools.NET as _AT
    import AssetsTools.NET.Extra as AT

    return _AT, AT, Cpp2IL


FieldsInfo = namedtuple(
    "FieldsInfo",
    "file_path file_name_fix is_bundle cab_name class_name asset_name container_path path_id value",
)


def try_serialize_str(s: str):
    try:
        return json.loads(s)
    except:
        return s


Assets = namedtuple("Assets", "file_inst asset_name file_path file_name_fix")


class AssetsTools:
    __intense__ = None
    resource_is_loaded = False

    game_data_dir: Path

    _AT: object
    AT: object
    Cpp2IL: object

    is_load_Assemblies: bool
    manager: object

    assets: dict[str, Assets] = {}
    container = {}

    def __init__(self, game_data_dir: Path, is_load_Assemblies=True):
        self.game_data_dir = game_data_dir
        self.is_load_Assemblies = is_load_Assemblies

        Managed_DIR = self.game_data_dir / "Managed"
        is_MonoCecil = Managed_DIR.exists()
        self._AT, self.AT, self.Cpp2IL = pythonnet_init(is_MonoCecil)

        self.manager = self.AT.AssetsManager()
        self.manager.LoadClassPackage(CLASSDATATPK_DIR)
        if is_load_Assemblies:
            self.load_Assemblies(is_MonoCecil)

    def load_Assemblies(self, is_MonoCecil):
        # fmt: off
        if is_MonoCecil:
            TempGenerator = self.AT.MonoCecilTempGenerator(Path_str(self.game_data_dir / "Managed"))
        else:
            il2cppFiles = self.Cpp2IL.FindCpp2IlFiles.Find(Path_str(self.game_data_dir))
            if il2cppFiles.success:
                TempGenerator = self.Cpp2IL.Cpp2IlTempGenerator(il2cppFiles.metaPath, il2cppFiles.asmPath)
        self.manager.MonoTempGenerator = TempGenerator
        # fmt: on

    def add_assets_cache(
        self, file_inst, asset_name: str, file_path: str, file_name_fix=""
    ):
        self.assets[asset_name] = Assets(file_inst, asset_name, file_path, file_name_fix)

    def load_asset(self, asset_path: str, stream=None):
        if stream is None:
            stream = File.OpenRead(str(asset_path))

        afileInst = self.manager.LoadAssetsFile(stream, asset_path, True)
        afile = afileInst.file
        afile.GenerateQuickLookup()
        self.manager.LoadClassDatabaseFromPackage(afile.Metadata.UnityVersion)
        self.add_assets_cache(afileInst, afileInst.name, asset_path)
        return afileInst

    def load_asset_bundle(self, bundle_path: str, stream=None):
        if stream is None:
            stream = File.OpenRead(str(bundle_path))
            
        bunInst = self.manager.LoadBundleFile(stream, bundle_path, True)
        file_name_fix = ""
        if Path(bunInst.path) != Path(bundle_path):
            file_name_fix = "_name_fix"
            bunInst = self.manager.LoadBundleFile(stream, bundle_path + file_name_fix, True)

        for cab_name in bunInst.file.GetAllFileNames():
            if cab_name.endswith(".resS") or cab_name.endswith(".resource"):
                continue
            afileInst = self.manager.LoadAssetsFileFromBundle(bunInst, cab_name, False)
            if afileInst is None:
                continue
            afile = afileInst.file
            afile.GenerateQuickLookup()
            self.manager.LoadClassDatabaseFromPackage(afile.Metadata.UnityVersion)
            self.add_assets_cache(afileInst, cab_name, bundle_path, file_name_fix)
        return bunInst

    def load_resources(self):
        if self.resource_is_loaded:
            return True

        ggm_path = self.game_data_dir / "globalgamemanagers"
        if not ggm_path.exists():
            return False

        ggm = self.manager.LoadAssetsFile(Path_str(ggm_path), True)
        ggm.file.GenerateQuickLookup()
        self.manager.LoadClassDatabaseFromPackage(ggm.file.Metadata.UnityVersion)

        for info in ggm.file.Metadata.AssetInfos:
            type = self.manager.ClassDatabase.FindAssetClassByID(info.TypeId)
            if not type:
                continue
            typeName = self.manager.ClassDatabase.GetString(type.Name)
            if typeName == "ResourceManager":
                baseField = self.manager.GetBaseField(ggm, info)
                m_Container = baseField["m_Container.Array"]
                for item in m_Container.Children:
                    path = item["first"].AsString
                    pointerField = item["second"]
                    assetExt = self.manager.GetExtAsset(ggm, pointerField, True)
                    assetInfo = assetExt.info
                    if assetInfo is None:
                        continue
                    assetType = self.manager.ClassDatabase.FindAssetClassByID(
                        assetInfo.TypeId
                    )
                    if assetType is None:
                        continue
                    assetTypeName = self.manager.ClassDatabase.GetString(assetType.Name)
                    assetName = self.AT.AssetHelper.GetAssetNameFast(
                        assetExt.file.file, self.manager.ClassDatabase, assetInfo
                    )

                    if self.container.get(assetTypeName) is None:
                        self.container[assetTypeName] = {}

                    self.container[assetTypeName][assetName] = path.lower()
        self.resource_is_loaded = True
        return True

    def _get_value(self, base_field):
        VType = self._AT.AssetValueType

        if base_field.Children.Count != 0:
            return self.dump_children(base_field)

        if base_field.Value is None:
            return {}

        if base_field.Value.ValueType in [
            VType.Int16,
            VType.Int32,
            VType.Int8,
        ]:
            return base_field.Value.AsInt
        if base_field.Value.ValueType == VType.Int64:
            return base_field.Value.AsLong
        if base_field.Value.ValueType in [
            VType.UInt16,
            VType.UInt32,
            VType.UInt8,
        ]:
            return base_field.Value.AsUInt
        if base_field.Value.ValueType == VType.UInt64:
            return base_field.Value.AsULong
        if base_field.Value.ValueType == VType.Float:
            return base_field.Value.AsFloat
        if base_field.Value.ValueType == VType.Double:
            return base_field.Value.AsDouble
        if base_field.Value.ValueType == VType.String:
            return try_serialize_str(base_field.Value.AsString)
        if base_field.Value.ValueType == VType.Bool:
            return base_field.Value.AsBool
        if base_field.Value.ValueType == VType.Array:
            if base_field.Value.AsArray.size == 0:
                return []
            raise NotImplementedError("array")
            return [
                self.dump_children(base_field.Value.AsArray[i])
                for i in range(base_field.Value.AsArray.size)
            ]

        if base_field.Value.ValueType == VType.ByteArray:
            if base_field.Value.AsByteArray.Length > 0:
                base_field.Value.AsByteArray.Length
            return list(base_field.Value.AsByteArray)

        if base_field.Value.ValueType == VType.ManagedReferencesRegistry:
            references = base_field.Value.AsManagedReferencesRegistry.references
            children = []
            for ref in references:
                if ref.data.TypeName == "DUMMY":
                    if ref.data.Value is not None:
                        raise NotImplementedError("??")
                    continue
                children.append(self.dump_children(ref.data))
            return children

        raise NotImplementedError(
            f"Unknown value type {base_field.Value.ValueType.ToString()}"
        )

    def dump_children(self, base_field, is_array=False):

        if base_field.Children.Count != 0:
            res_obj = {}
            res_list = []
            for child in base_field:
                if child.FieldName == "Array" or is_array:
                    if is_array and child.FieldName == "data":
                        res_list.append(self.dump_children(child))
                    else:
                        res_list.append(self.dump_children(child, True))
                else:
                    data = self.dump_children(child)
                    if isinstance(data, list) and len(data) == 1:
                        data = data[0]
                    res_obj[child.FieldName] = data
            return res_list if len(res_list) > 0 else res_obj

        if base_field.TypeName == "string":
            str_value = try_serialize_str(base_field.AsString)
            return str_value

        return self._get_value(base_field)

    def filter_type(self, file_inst, asset_classId: AssetClassID):
        assets_type = self.AT.AssetClassID(asset_classId.value)
        return file_inst.file.GetAssetsOfType(assets_type)

    def dump_monobehaviour(self, as_json: bool = False, handler: callable = None):
        script_obj = {}

        def dump_script(asset: Assets, go_base):
            
            for goInfo in go_base:
                try:
                    goBase = self.manager.GetBaseField(asset.file_inst, goInfo)
                except Exception as e:
                    logger.error(f"field load:{asset.file_path} PathId:[{goInfo.PathId}] Source:{e.Source} Message:{e.Message}")
                    continue

                type_name = goBase.TypeName
                asset_name = self.AT.AssetHelper.GetAssetNameFast(
                    asset.file_inst.file, self.manager.ClassDatabase, goInfo
                )

                container_path = self.container.get(type_name)
                if container_path is None:
                    container_path = ""
                else:
                    container_path = container_path.get(asset_name, "")

                if type_name == "TextAsset":
                    class_name = type_name
                    value = try_serialize_str(goBase["m_Script"].AsString)

                else:
                    scriptBaseField = self.manager.GetExtAsset(asset.file_inst, goBase["m_Script"]).baseField

                    if scriptBaseField is None:
                        continue

                    class_name = scriptBaseField["m_Name"].AsString

                    value = self.dump_children(goBase)

                is_bundle = bool(asset.file_inst.parentBundle)
                fi = FieldsInfo(
                    file_path=str(
                        Path(asset.file_path).relative_to(self.game_data_dir.parent)
                    ),
                    file_name_fix=asset.file_name_fix,
                    is_bundle=is_bundle,
                    cab_name=asset.file_inst.name if is_bundle else "",
                    class_name=class_name,
                    asset_name=asset_name,
                    container_path=container_path,
                    path_id=goInfo.PathId,
                    value=value,
                )

                if as_json:
                    fi = fi._asdict()

                if script_obj.get(class_name) is None:
                    script_obj[class_name] = [fi]
                else:
                    script_obj[class_name].append(fi)

        for assets in self.assets.values():
            if assets.asset_name == "globalgamemanagers.assets":
                continue
            
            MonoBehaviour = self.filter_type(
                assets.file_inst, AssetClassID.MonoBehaviour
            )
            # MonoScript = self.filter_type(file_inst, AssetClassID.MonoScript)
            TextAsset = self.filter_type(assets.file_inst, AssetClassID.TextAsset)

            if handler is not None:
                total_info_num = len(MonoBehaviour) + len(TextAsset)
                # total_info_num = len(TextAsset)
                handler(total_info_num)

            dump_script(assets, MonoBehaviour)
            # dump_script(file_inst, MonoScript)
            dump_script(assets, TextAsset)

        return script_obj

    def update_monobehaviour(self, update_script_obj: dict):

        logger.info("collecting data")

        all_data = defaultdict(
            lambda: {
                "is_bundle": False,
                "cab": defaultdict(list),
                "asset": defaultdict(list),
            }
        )
        for _script_obj in update_script_obj:
            fi = _script_obj["info"]
            file_path = Path_str(self.game_data_dir.parent / fi["file_path"])
            all_data[file_path]["is_bundle"] = fi["is_bundle"]
            if fi["is_bundle"]:
                all_data[file_path]["cab"][fi["cab_name"]].append(_script_obj)
            else:
                all_data[file_path]["asset"][file_path].append(_script_obj)

        afileInstCache = {}

        for file_path, data in all_data.items():
            is_bundle = data["is_bundle"]
            bunInst = None

            if is_bundle:
                # bunInst = self.manager.LoadBundleFile(file_path, True)
                    bunInst = self.load_asset_bundle(file_path)

            data_list = data["cab"] if is_bundle else data["asset"]

            for cab_name, assets in data_list.items():

                if is_bundle:
                    afileInst = self.manager.LoadAssetsFileFromBundle(bunInst, cab_name, True)
                else:
                    # afileInst = self.manager.LoadAssetsFile(file_path, True)
                    afileInst = self.load_asset(file_path)

                afile = afileInst.file
                # afile.GenerateQuickLookup()
                # self.manager.LoadClassDatabaseFromPackage(afile.Metadata.UnityVersion)
                afileInstCache[file_path] = afileInst

                with tqdm(total=len(assets), desc=f"update {cab_name}") as pbar:
                    path_cache = {}

                    for _script_obj in assets:
                        pbar.update(1)
                        path_id = _script_obj["info"]["path_id"]
                        
                        if path_cache.get(path_id) is not None:
                            goInfo, goBase = path_cache[path_id]
                        else:
                            goInfo = afile.GetAssetInfo(path_id)
                            goBase = self.manager.GetBaseField(afileInst, goInfo)
                            
                            if goBase.TypeName == "TextAsset":
                                ...
                            else:
                                scriptBaseField = self.manager.GetExtAsset(afileInst, goBase["m_Script"]).baseField

                                if scriptBaseField is None:
                                    continue

                            path_cache[path_id] = (goInfo, goBase)

                        goBaseField = goBase
                        
                        # if goBaseField.TypeName == "TextAsset" and path_id in json_value_path:
                        #     continue
                        
                        if goBaseField.TypeName == "TextAsset":
                            
                            
                            def update_str_obj(str_obj, paths, field, value):
                                replace_obj = json.loads(str_obj)
                                replace_obj_obj = replace_obj
                                
                                for _path in paths:
                                    if "[" in _path and _path.endswith("]"):
                                        _path_arr = _path.split("[")
                                        for _index, _field in enumerate(_path_arr):
                                            if field == "" and _path_arr[-1].endswith("]") and _index == len(_path_arr) - 1:
                                                field = int(_field.rstrip("]"))
                                            elif _field.endswith("]"):
                                                replace_obj_obj = replace_obj_obj[int(_field.rstrip("]"))]
                                            elif _field == "value":
                                                continue
                                            else:
                                                replace_obj_obj = replace_obj_obj.get(_field)
                                    elif isinstance(replace_obj_obj.get(_path), dict):
                                        replace_obj_obj = replace_obj_obj.get(_path)
                                
                                replace_obj_obj[field] = value
                                replace_text = json.dumps(replace_obj, ensure_ascii=False)
                                return replace_text
                            
                            
                            str_obj = goBaseField["m_Script"].AsString
                            full_path = _script_obj["full_path"].split(".")[1:]
                            field = _script_obj['field']
                            value = _script_obj['value']
                            
                            if isinstance(_script_obj["info"]["value"], list):
                                replace_text = update_str_obj(str_obj, full_path, field, value)
                                goBaseField["m_Script"].AsString = replace_text
                                continue
                            elif isinstance(_script_obj["info"]["value"], dict):
                                replace_text = update_str_obj(str_obj, full_path, field, value)
                                goBaseField["m_Script"].AsString = replace_text
                                continue
                            
                            replace_text = _script_obj["value"]
                            if goBaseField["m_Script"].AsString != replace_text:
                                goBaseField["m_Script"].AsString = replace_text
                                continue

                        _script_obj_full_path = _script_obj["full_path"].split(".")[2:]

                        for _path in _script_obj_full_path:
                            if "[" in _path and _path.endswith("]"):
                                for _field in _path.split("["):
                                    if _field.endswith("]"):
                                        goBaseField = goBaseField[int(_field.rstrip("]"))]
                                    else:
                                        goBaseField = goBaseField[_field + ".Array"]
                            else:
                                goBaseField = goBaseField[_path]

                        data_info = None

                        if goBaseField.TypeName == "string":
                            data_info = goBaseField
                        elif goBaseField.TypeName == "TextAsset":
                            data_info = goBaseField["m_Script"]
                        else:
                            raise NotImplementedError(
                                f"not support type [{goBaseField.TypeName}]"
                            )

                        if data_info.AsString != _script_obj["value"]:
                            data_info.AsString = _script_obj["value"]

                    for goInfo, goBase in path_cache.values():
                        goInfo.SetNewData(goBase)

                if is_bundle:
                    # fmt: off
                    fileIndex = list(bunInst.file.GetAllFileNames()).index(cab_name)
                    # bunInst.file.BlockAndDirInfo.DirectoryInfos[fileIndex].SetNewData(afile);
                    bunInst.file.BlockAndDirInfo.DirectoryInfos[fileIndex].Replacer = self._AT.ContentReplacerFromAssets(afile)
                    # fmt: on

        logger.info("writing assets to file")
        for afileInst in afileInstCache.values():
            self.save_assets(afileInst)

    def save_assets(self, afileInst):
        is_bundle = bool(afileInst.parentBundle)
        file_name_fix = ""
        if is_bundle:
            if assets := self.assets.get(afileInst.name):
                file_name_fix = assets.file_name_fix
                
            afileInst = afileInst.parentBundle
            

        temp_path = afileInst.path
        
        if file_name_fix:
            temp_path = temp_path.replace(file_name_fix, "")
        
        temp_mod_path = temp_path + ".mod"
        writer = self._AT.AssetsFileWriter(temp_mod_path)
        afileInst.file.Write(writer)
        writer.Close()
        afileInst.file.Close()

        logger.info(f"save file [{temp_path}]")
        if is_bundle:
            self.compresses_asset_bundle(temp_mod_path, output_path=temp_path)
        else:
            Path(temp_path).unlink()
            Path(temp_mod_path).rename(temp_path)

    def compresses_asset_bundle(self, bundle_path: str, output_path: str):
        logger.info(f"compress file [{bundle_path}]")

        newUncompressedBundle = self._AT.AssetBundleFile()
        newUncompressedBundle.Read(
            self._AT.AssetsFileReader(File.OpenRead(bundle_path))
        )

        writer = self._AT.AssetsFileWriter(output_path + ".compressed")
        newUncompressedBundle.Pack(writer, self._AT.AssetBundleCompressionType.LZ4)

        writer.Close()
        newUncompressedBundle.Close()

        Path(bundle_path).unlink()
        Path(output_path).unlink()
        Path(output_path + ".compressed").rename(output_path)

        logger.info(f"compress file [{output_path}]")
