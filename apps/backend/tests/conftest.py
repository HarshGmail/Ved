import io
import os

import pytest
import pytest_asyncio
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from ved_db.testing import drop_schema, guard_test_url, recreate_schema

TEST_DATABASE_URL = os.environ.get("VED_TEST_DATABASE_URL")

requires_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set VED_TEST_DATABASE_URL to run database-backed tests",
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(guard_test_url(TEST_DATABASE_URL))
    await recreate_schema(engine)

    yield async_sessionmaker(engine, expire_on_commit=False)

    await drop_schema(engine)
    await engine.dispose()


PAGE_WIDTH_POINTS = 612
PAGE_HEIGHT_POINTS = 792
LINE_HEIGHT_POINTS = 14
TOP_MARGIN_POINTS = 720
LEFT_MARGIN_POINTS = 72


def escape_pdf_text(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def page_content(lines: list[str]) -> bytes:
    commands = [
        "BT /F1 11 Tf",
        f"{LINE_HEIGHT_POINTS} TL",
        f"{LEFT_MARGIN_POINTS} {TOP_MARGIN_POINTS} Td",
    ]
    commands += [f"({escape_pdf_text(line)}) Tj T*" for line in lines]
    commands.append("ET")
    return "\n".join(commands).encode("latin-1")


def build_pdf(pages: list[list[str]]) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for lines in pages:
        page = writer.add_blank_page(PAGE_WIDTH_POINTS, PAGE_HEIGHT_POINTS)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        content = DecodedStreamObject()
        content.set_data(page_content(lines))
        page.replace_contents(content)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def make_pdf():
    return build_pdf
