from types import SimpleNamespace

from mcp import Client

from ved_snappy.server import api_key_from, mcp

TOOL_NAMES = {
    "search_photos",
    "list_people",
    "photos_of_person",
    "list_albums",
    "album_photos",
    "recent_photos",
    "photo_details",
}


async def test_the_server_offers_the_read_only_photo_tools():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools.tools} == TOOL_NAMES


async def test_a_call_without_a_key_is_a_readable_tool_error():
    async with Client(mcp) as client:
        result = await client.call_tool("list_albums", {})

    assert result.is_error is True
    assert "no snappy API key was sent" in str(result.content)


def test_the_key_comes_from_the_authorization_header_only():
    context = SimpleNamespace(headers={"Authorization": "Bearer key-one"})

    assert api_key_from(context) == "key-one"
    assert (
        api_key_from(SimpleNamespace(headers={"authorization": "Bearer key-two"}))
        == "key-two"
    )
