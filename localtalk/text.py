import re


MIN_CHUNK_CHARS = 20
SENTENCE_END = re.compile(r"[。！？!?；;\n]|\.(?=\s)")
FIRST_CHUNK_END = re.compile(r"[，：]|(?<!\d)[,:]|" + SENTENCE_END.pattern)


class TextChunks:
    def __init__(self, config):
        self.config = config
        self.buffer = ""
        self.first = True
        self.previous_chars = 0

    def feed(self, text, final=False):
        self.buffer += text
        while self.buffer:
            limit = self.config["first_chunk_chars" if self.first else "chunk_chars"]
            if not self.first:
                # 按中文字符数近似约束下一段耗时，避免短音频之后突然合成长段。
                limit = min(limit, max(MIN_CHUNK_CHARS, self.previous_chars * 3 // 2))
            end = 0
            pattern = FIRST_CHUNK_END if self.first else SENTENCE_END
            for match in pattern.finditer(self.buffer):
                if MIN_CHUNK_CHARS <= match.end() <= limit and re.search(
                    r"\w", self.buffer[: match.end()]
                ):
                    end = match.end()
                    break
            if not end and len(self.buffer) >= limit:
                # 长句优先在逗号或空格处分段；没有边界时保留全部字符硬切。
                boundaries = list(re.finditer(r"[，,、：:\s]", self.buffer[:limit]))
                end = boundaries[-1].end() if boundaries else limit
                if end < max(MIN_CHUNK_CHARS, limit // 2):
                    end = limit
            if not end:
                if not final:
                    break
                end = len(self.buffer)
            chunk, self.buffer = self.buffer[:end], self.buffer[end:]
            if chunk.strip():
                self.first = False
                self.previous_chars = len(chunk.strip())
                yield chunk
