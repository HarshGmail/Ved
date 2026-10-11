from ved_backend.chunking import (
    CHUNK_OVERLAP_CHARS,
    MAX_CHUNK_CHARS,
    TARGET_CHUNK_CHARS,
    Page,
    chunk_pages,
    overlap_tail,
    paragraphs,
)

WORDS = ("tenant", "deposit", "landlord", "premises", "agreement", "notice")


def prose(word_count: int, offset: int = 0) -> str:
    return " ".join(
        f"{WORDS[(offset + index) % len(WORDS)]}{offset + index}"
        for index in range(word_count)
    )


def every_word_is_whole(chunk_text: str, source: str) -> bool:
    source_words = set(source.split())
    return all(word in source_words for word in chunk_text.split())


def test_paragraphs_collapse_whitespace_and_drop_blanks():
    text = "first  line\nstill first\n\n\n   \n\nsecond"

    assert paragraphs(text) == ["first line still first", "second"]


def test_short_paragraphs_share_one_chunk():
    chunks = chunk_pages([Page(text="one\n\ntwo\n\nthree")])

    assert [chunk.text for chunk in chunks] == ["one\n\ntwo\n\nthree"]


def test_chunks_stay_within_the_size_cap():
    text = "\n\n".join(prose(60, offset) for offset in range(0, 1200, 60))

    chunks = chunk_pages([Page(text=text)])

    assert len(chunks) > 1
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS for chunk in chunks)


def test_a_chunk_past_the_target_is_closed_before_it_reaches_the_cap():
    paragraph = prose(15)
    text = "\n\n".join([prose(80), paragraph])

    first, second = chunk_pages([Page(text=text)])

    assert len(first.text) >= TARGET_CHUNK_CHARS
    assert second.text.endswith(paragraph)


def test_a_long_paragraph_is_never_cut_mid_word():
    text = prose(900)

    chunks = chunk_pages([Page(text=text)])

    assert len(chunks) > 1
    assert all(every_word_is_whole(chunk.text, text) for chunk in chunks)


def test_neighbouring_chunks_overlap():
    text = prose(900)

    first, second, *_ = chunk_pages([Page(text=text)])

    shared = overlap_tail(first.text)
    assert shared
    assert second.text.startswith(shared)
    assert len(shared) <= CHUNK_OVERLAP_CHARS


def test_overlap_carries_across_paragraph_boundaries():
    text = "\n\n".join(prose(60, offset) for offset in range(0, 600, 60))

    first, second, *_ = chunk_pages([Page(text=text)])

    assert second.text.startswith(overlap_tail(first.text))


def test_overlap_starts_on_a_word_boundary():
    tail = overlap_tail("alpha " + "b" * 200 + " gamma delta", overlap=20)

    assert tail == "gamma delta"


def test_chunks_keep_their_page_number_and_count_across_pages():
    chunks = chunk_pages(
        [Page(text="cover", number=1), Page(text="the deposit clause", number=2)]
    )

    assert [(chunk.ordinal, chunk.page_number) for chunk in chunks] == [(0, 1), (1, 2)]


def test_a_blank_page_yields_no_chunks():
    chunks = chunk_pages([Page(text="  \n\n ", number=1), Page(text="hi", number=2)])

    assert [chunk.page_number for chunk in chunks] == [2]
    assert chunks[0].ordinal == 0


def test_a_single_word_longer_than_a_chunk_is_split_rather_than_lost():
    word = "x" * (MAX_CHUNK_CHARS * 2)

    chunks = chunk_pages([Page(text=word)])

    assert "".join(chunk.text for chunk in chunks) == word
