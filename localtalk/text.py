import re


SENTENCE_END = re.compile(r"""[。！？!?]+[”’"」』）】》]*|\.(?=\s)|\n""")
EARLY_END = re.compile(r"[。！？!?，、；：;\n]|(?<!\d)[,:]|\.(?=\s)")
SOFT_END = re.compile(r"[，、；：;]|(?<!\d)[,:](?!\d)|\s")


class TextChunks:
    def __init__(self, config):
        tts = config["tts"]
        chunking = tts[tts["backend"]]["chunking"]
        self.limit = tts["chunk_chars"]
        self.minimums = (
            chunking["first_min_chars"],
            chunking["second_min_chars"],
            chunking["later_min_chars"],
        )
        self.buffer = ""
        self.chunks = 0

    def feed(self, text, final=False):
        self.buffer += text
        while self.buffer:
            early = self.chunks < 2
            minimum = self.minimums[min(self.chunks, 2)]
            boundary = EARLY_END if early else SENTENCE_END
            end = 0
            for match in boundary.finditer(self.buffer):
                if match.end() > self.limit:
                    break
                # 前两段遇到标点立即提交，后续段留一个字符观察句尾引号。
                if minimum <= match.end() and (
                    early or final or match.end() < len(self.buffer)
                ):
                    end = match.end()
                    break
            if not end and len(self.buffer) > self.limit:
                for match in SOFT_END.finditer(self.buffer[: self.limit + 1]):
                    if minimum <= match.end() <= self.limit:
                        end = match.end()
                if not end:
                    end = self.limit
            if not end:
                if not final:
                    break
                end = len(self.buffer)
            chunk, self.buffer = self.buffer[:end], self.buffer[end:]
            if chunk.strip():
                self.chunks += 1
            yield chunk
