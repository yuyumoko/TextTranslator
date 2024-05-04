import functools
import inspect
import base64
import typing as t
from pathlib import Path
from pydantic import BaseModel, validator
from tenacity import _utils
from .simple_config import SimpleConfig


class ArgRequireOption(BaseModel):
    input_fn: t.Callable = input

    msg_format: str = "{msg} :"
    msg_default_format: str = "{msg} 默认[{default}] :"

    save: bool = False
    save_path: str | Path = Path("config.ini")
    save_prefix: str = "arg_"

    @validator("save_path", pre=True)
    def save_path_to_path(cls, v):
        return Path(v)


def encode_val(val: str):
    return base64.b64encode(val.encode("utf-8")).decode("utf-8")


def decode_val(val: str):
    return base64.b64decode(val.encode("utf-8")).decode("utf-8")


class ArgRequire:
    """用于获取用户输入的装饰器

    例子:
    ag = ArgRequire(ArgRequireOption(save=True, save_path="config.ini"))

    def input_fn(msg):
        # 自定义输入函数
        print("input_fn")
        return input(msg)

    @ag.apply("请输入arg1", "请输入arg2")
    # @ag.apply(arg2="请输入arg2", arg1=("请输入arg1", "4445"))
    # @ag.apply(input_fn, "请输入arg1", "请输入arg2")
    # @ag.apply
    def test1(arg1: int, arg2: Path):
        print("test1")

    apply 会将装饰器下面的函数的参数名和提示信息对应起来, 并且会自动将用户输入的值转换为对应的类型


    if __name__ == "__main__":
        test1()
    """

    __slots__ = ("input_fn", "option", "config")

    def __init__(self, option: ArgRequireOption = None):
        if option is None:
            option = ArgRequireOption()
        self.input_fn = option.input_fn
        self.option = option
        self.config = SimpleConfig(option.save_path)

    def call_input_fn(
        self,
        annotation,
        msg: str | tuple[str, t.Any],
        input_fn: t.Callable = None,
        once: bool = False,
    ):
        default = ""
        if isinstance(msg, tuple):
            msg, default = msg
            msg = self.option.msg_default_format.format(msg=msg, default=default)
        else:
            msg = self.option.msg_format.format(msg=msg)

        if input_fn is None:
            input_fn = self.input_fn

        if not once:
            raw_val = input_fn(msg) or default
        else:
            raw_val = default

        if isinstance(raw_val, str) and annotation == bool:
            val = self.__apply_raw_bool_val(raw_val, annotation)
            return val, raw_val

        if annotation == Path:
            path_str = raw_val.replace('"', "").replace("'", "")
            path_str = path_str[1:].lstrip() if path_str.startswith("&") else path_str
            return Path(path_str), raw_val

        if annotation != inspect._empty:
            val = annotation(raw_val)
        else:
            val = raw_val

        return val, raw_val

    def read_local_items(self, func: t.Callable):
        fn_name = _utils.get_callback_name(func)
        section_key = self.option.save_prefix + fn_name
        if self.config.has_section(section_key):
            items = self.config.items(section_key)
            if not items:
                return []
            for i, (k, v) in enumerate(items):
                if k.endswith("_encode"):
                    items[i] = (k[:-7], decode_val(v))
            return items

    def save(self, func: t.Callable, kwargs: dict[str, t.Any]):
        fn_name = _utils.get_callback_name(func)
        for arg, val in kwargs.items():
            if "%" in val:
                val = encode_val(val)
                arg += "_encode"
            self.config.set(self.option.save_prefix + fn_name, arg, val)

    def remove(self, func: t.Callable):
        fn_name = _utils.get_callback_name(func)
        self.config.remove_section(self.option.save_prefix + fn_name)

    def __apply_arg_pop(self, _args, current: bool):
        res = None
        if _args and current:
            res = _args[0]
            _args = _args[1:]
        return res, _args

    def __apply_raw_bool_val(self, raw_val: t.Any, annotation: t.Any, ret_str=False):
        if isinstance(raw_val, bool):
            return str(raw_val).lower()

        if isinstance(raw_val, str) and annotation == bool:
            _raw_val = raw_val.lower()
            if _raw_val in ["true", "yes", "y", "1"]:
                if ret_str:
                    return self.__apply_raw_bool_val(True, annotation)
                return True
            elif _raw_val in ["false", "no", "n", "0"]:
                if ret_str:
                    return self.__apply_raw_bool_val(False, annotation)
                return False
            else:
                raise ValueError(f"无法将{raw_val}转换为bool类型 , 请使用true或false")

        return raw_val

    def apply(self, *_args, **_kwargs):
        if len(_args) == 1 and callable(_args[0]):
            return self.apply()(_args[0])
        else:
            input_fn, _args = self.__apply_arg_pop(_args, callable(_args[0]))
            once, _args = self.__apply_arg_pop(_args, isinstance(_args[0], bool))

            def decorator(func: t.Callable):
                @functools.wraps(func)
                def wrapper(*args, **kwargs):
                    fn = inspect.signature(func)
                    params = fn.parameters
                    func_keys = list(params.keys())

                    if not _args and not _kwargs:
                        t_kwargs = dict(zip(func_keys, func_keys))
                    else:
                        t_kwargs = _kwargs

                    input_kwargs_raw = {}

                    local_items = self.read_local_items(func)

                    def update_kw(arg, msg):
                        annotation = params[arg].annotation

                        has_default_val = False
                        if local_items:
                            default_val = list(
                                filter(lambda x: x[0] == arg.lower(), local_items)
                            )
                            if default_val:
                                if isinstance(msg, tuple):
                                    msg = msg[0]
                                _val = self.__apply_raw_bool_val(
                                    default_val[0][1], annotation
                                )
                                msg = (msg, _val)
                                has_default_val = True

                        val, raw_val = self.call_input_fn(
                            annotation, msg, input_fn, once and has_default_val
                        )

                        input_kwargs_raw[arg] = self.__apply_raw_bool_val(
                            raw_val, annotation, True
                        )
                        kwargs[arg] = val

                    for i, msg in enumerate(_args):
                        if i < len(args):
                            continue
                        arg = func_keys[i]
                        if arg in kwargs and not kwargs[arg] is None:
                            continue
                        update_kw(arg, msg)

                    for arg, msg in t_kwargs.items():
                        if arg in kwargs:
                            continue
                        update_kw(arg, msg)

                    func_ret = func(*args, **kwargs)

                    if self.option.save:
                        self.save(func, input_kwargs_raw)

                    return func_ret

                return wrapper

            return decorator
