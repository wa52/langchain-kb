from langchain_text_splitters import RecursiveCharacterTextSplitter


def create_splitter(chunk_size: int = 500, chunk_overlap: int = 80):
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n## ", "\n### ", "\n```\n", "\n\n", "\n", "。", ".", " ", ""],
        keep_separator=False,
    )
