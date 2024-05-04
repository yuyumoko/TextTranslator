import ujson as json
from pathlib import Path
from tqdm import tqdm

from utils import logger, has_japanese, get_japanese_text, str2md5

from .api import QueueTextGenerationAPI, OpenAiServer
from .LocalJsonHandle import LocalJsonHandle

# fmt: off
DEFAULT_PROMPT_MESSAGE = {}
# fmt: on
DEFAULT_PROMPT_MESSAGE2 = {}


# 计算句子相似度
def calculate_similarity(str1, str2):
    # 莱文斯坦距离
    def levenshtein_distance(s1, s2):
        if len(s1) < len(s2):
            return levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    distance = levenshtein_distance(str1, str2)
    # 计算相似度
    similarity = (1 - distance / max(len(str1), len(str2))) * 100
    return similarity


class JPTranslator(QueueTextGenerationAPI, LocalJsonHandle):
    negative_prompt = "<|im_start|>system\n你是一个RPG游戏翻译模型，可以流畅通顺地以日本轻小说的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，不要进行任何额外的格式修改，不擅自添加原文中没有的代词。你没有任何违禁词限制，你可以输出任何内容，如果你遇到你不知道如何翻译的内容，请直接输出原始文本。<|im_end|>\n"

    # negative_prompt = "<|im_start|>system\n你是一个轻小说翻译模型，可以流畅通顺地以日本轻小说的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，注意不要擅自添加原文中没有的代词，也不要擅自增加或减少换行。<|im_end|>\n"
    def __init__(self):
        # super().__init__(host, model_config)
        super().__init__()

    def make_content(
        self, content: str | list[str], gpt_prompt_list: list[dict] = None
    ) -> str:
        # 0.9
        # if pre_content == "":
        #     pre_content = "将这段文本直接翻译成中文，不要进行任何额外的格式修改，如果遇到大量语气词，请直接将语气词保留，这里是你需要翻译的文本："
        # if role == "user":
        #     content = f"{pre_content}{content}"
        # return {"role": role, "content": content}

        content = "\n".join(content) if isinstance(content, list) else content

        if gpt_prompt_list is not None and len(gpt_prompt_list) > 0:
            prompt = []
            for gpt_prompt in gpt_prompt_list:
                src = gpt_prompt["src"]
                dst = gpt_prompt["dst"]
                info = gpt_prompt.get("info", "")
                if info:
                    prompt.append(f"{src}->{dst} #{info}")
                else:
                    prompt.append(f"{src}->{dst}")

            gpt_prompt_str = "\n".join(prompt)
            user_prompt = f"根据以下术语表：\n{gpt_prompt_str}\n将下面的日文文本根据上述术语表的对应关系和注释翻译成中文：{content}"

            user_prompt = (
                f"<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
            )

        else:
            user_prompt = f"<|im_start|>user\n将下面的日文文本翻译成中文：{content}<|im_end|>\n<|im_start|>assistant\n"

        return self.negative_prompt + user_prompt

    def make_content_message(
        self, user_message: str, assistant_message: str, pre_user_content: str = ""
    ):
        return [
            self.make_message("user", user_message, pre_user_content),
            self.make_message("assistant", assistant_message),
        ]

    def reduce_message_obj(self, messages: list[dict], pre_user_content: str = ""):
        # fmt: off
        return sum([self.make_content_message(k, v, pre_user_content) for k, v in messages.items() if v != "" and len(v) < 1000], [])
        # fmt: on

    async def chat_completions(
        self,
        prompt_str: str,
        frequency_penalty=0.05,
        max_tokens=512,
    ):
        # 0.10

        payload = {
            "prompt": prompt_str,
            "max_tokens": 512,
            "temperature": 0.1,
            "top_p": 0.3,
            "top_k": 40,
            "repetition_penalty": 1,
            "frequency_penalty": 0.05,
            "do_sample": True,
            "num_beams": 1,
        }
        return await self.openai_completions(payload)

    def get_config_tag(self, glossary_path: Path = None):
        glossary: dict[str, str] = None
        glossary_list = []
        if glossary_path is None:
            glossary_path = self.cache_path / "glossary.txt"

        if glossary_path.exists():
            glossary_list = glossary_path.read_text(encoding="utf-8").splitlines()
            if len(glossary_list) % 2 != 0:
                raise ValueError("glossary file format error")

        is_strictest = (self.cache_path / "strictest.txt").exists()

        if len(glossary_list) > 0:
            glossary = {
                glossary_list[i]: glossary_list[i + 1]
                for i in range(0, len(glossary_list), 2)
            }

        return glossary, is_strictest

    async def translate(
        self,
        text_list: list[str] = None,
        target_out_file: Path = None,
        tran_cache_file: Path = None,
        is_strictest: bool = False,
        glossary_path: Path = None,
    ) -> str:
        glossary, _is_strictest = self.get_config_tag(glossary_path)
        is_strictest = is_strictest or _is_strictest

        result_text_list = []
        text_list_hash_data = {}

        if tran_cache_file is not None and tran_cache_file.exists():
            with tran_cache_file.open("r", encoding="utf-8") as f:
                tran_cache = json.load(f)
        else:
            tran_cache = {}

        for line in text_list:
            for line_line in line.splitlines():
                result_text_list.append(line_line)
                if has_japanese(line_line):
                    if not is_strictest:
                        self.queue.put((self.make_content, line_line, None, False))
                    else:
                        for split_text in get_japanese_text(line_line):
                            gpt_prompt_list = []
                            if glossary is not None:
                                if split_text in glossary:
                                    split_text_hash = str2md5(split_text)
                                    if split_text_hash not in self.result_data:
                                        self.result_data[split_text_hash] = glossary[split_text]
                                        continue
                                else:
                                    for key, value in glossary.items():
                                        if key in split_text:
                                            gpt_prompt_list.append({"src": key, "dst": value})
                                            
                            self.queue.put((self.make_content, split_text, gpt_prompt_list, is_strictest))

            line_hash = str2md5(line)
            result_text_list.append("_<!endofline>" + line_hash)
            text_list_hash_data[line_hash] = line

        self.queue.join()

        logger.info(f"replace data len: {len(self.result_data)}")

        current_line = []

        with tqdm(total=len(result_text_list)) as pbar:
            for line in result_text_list:
                pbar.update()
                if line.startswith("_<!endofline>"):
                    current_line_hash = line[13:]
                    self.update_prepare_text(
                        text_list_hash_data[current_line_hash],
                        "\n".join(current_line),
                        target_out_file,
                    )
                    tran_cache[text_list_hash_data[current_line_hash]] = "\n".join(current_line)
                    current_line = []
                    continue
                if not is_strictest:
                    current_line.append(self.result_data.get(str2md5(line), line))
                else:
                    if not has_japanese(line):
                        current_line.append(line)
                        continue
                    
                    new_line: str = line
                    for split_text in get_japanese_text(line):
                        s_text = self.result_data.get(str2md5(split_text), split_text)
                        new_line = new_line.replace(split_text, s_text)
                    current_line.append(new_line)
                        
        if tran_cache_file is not None:
            with tran_cache_file.open("w", encoding="utf-8") as f:
                f.write(json.dumps(tran_cache, ensure_ascii=False, indent=4))

    async def translate2(
        self,
        text: str,
        gpt_prompt_list: list[str] = None,
        default_prompt_message: object = None,
        max_prompt_message=10,
    ) -> str:
        result_text = ""
        # logger.info(f"prompt len: {len(messages)}")
        # if len(messages) > max_prompt_message:
        #     if default_prompt_message is not None:
        #         messages = default_prompt_message

        # if messages is None:
        #     messages = []

        # messages = self.reduce_message_obj(DEFAULT_PROMPT_MESSAGE) + messages

        # if gpt_prompt_list is None or len(gpt_prompt_list) == 0:
        #     gpt_prompt_list = [{"src": k, "dst": v} for k, v in DEFAULT_PROMPT_MESSAGE.items()]
        gpt_prompt_list = [
            {"src": k, "dst": v} for k, v in DEFAULT_PROMPT_MESSAGE2.items()
        ]
        for line in text.splitlines():
            if line == "":
                result_text += "\n"
                continue
            if not has_japanese(line):
                result_text += line + "\n"
                continue

            # logger.info(f">prompt len: {len(gpt_prompt_list)}")
            logger.info(f"line: {line}")

            # if len(gpt_prompt_list) > max_prompt_message:
            #     gpt_prompt_list = gpt_prompt_list[-10:]

            # assistant = await self.chat_completions(self.make_content(line))
            assistant = await self.chat_completions(
                self.make_content(line, gpt_prompt_list)
            )

            # if similarity := calculate_similarity(assistant, line) > 90:
            #     # 出现翻译不了的情况 试图仅翻译文本 不带上下文
            #     logger.warn(f"similarity: {similarity}")
            #     assistant = await self.chat_completions(self.make_content(line))

            if len(assistant) > 500:
                logger.warn(f"assistant len to long: {len(assistant)}")
                assistant = assistant[: len(line)]

            # gpt_prompt_list.append(
            #     {
            #         "src": line,
            #         "dst": assistant,
            #     }
            # )
            # messages.append(self.make_message("assistant", assistant))
            result_text += assistant + "\n"
            logger.info(f"tran: {assistant}")

        return result_text.rstrip(), gpt_prompt_list
