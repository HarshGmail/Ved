import asyncio
import json
from types import SimpleNamespace
from typing import Any

from ved_backend.agent import SYSTEM_PROMPT
from ved_backend.config import Settings
from ved_backend.tools.servers import configured_servers
from ved_backend.tools.toolbox import MCPToolbox, RemoteServer

CHARS_PER_TOKEN = 4
FAKE_PLAN_TOKEN = "fixture"

PLAN_TOOL_FIXTURE: list[tuple[str, str, dict[str, str], list[str]]] = [
    (
        "list_projects",
        "List the projects you can see, with their keys and open task counts.",
        {},
        [],
    ),
    (
        "list_my_tasks",
        (
            "Tasks assigned to you that are not done, highest priority first, then "
            "nearest due date."
        ),
        {},
        [],
    ),
    (
        "search_tasks",
        "Search tasks across your projects. All filters are optional.",
        {
            "projectId": "Project id or key",
            "epic": "Epic id",
            "assignee": "User id",
            "priority": "Priority",
            "label": "Label",
            "due": "Due filter",
            "before": "YYYY-MM-DDTHH:MM",
            "q": "Text in title, description, key or labels",
            "mine": "Assigned to me",
            "status": "Status",
            "includeDone": "Include done",
        },
        [],
    ),
    (
        "get_task",
        "Get one task with its comments.",
        {"task": "Task id or key such as DIW-12"},
        ["task"],
    ),
    (
        "create_task",
        "Create a task. Without a status it lands in the backlog.",
        {
            "projectId": "Project id or key such as DIW",
            "title": "Title",
            "description": "Description",
            "priority": "Priority",
            "status": "Status",
            "assigneeIds": "User ids",
            "epicId": "Epic id or key",
            "startDate": "YYYY-MM-DD",
            "dueDate": "YYYY-MM-DD",
            "startTime": "HH:MM",
            "dueTime": "HH:MM",
            "labels": "Labels",
        },
        ["projectId", "title"],
    ),
    (
        "update_task",
        "Change fields of a task. Only the fields you pass change.",
        {
            "task": "Task id or key",
            "title": "Title",
            "description": "Description",
            "priority": "Priority",
            "status": "Status",
            "assigneeIds": "User ids",
            "epicId": "Epic id or key",
            "startDate": "YYYY-MM-DD",
            "dueDate": "YYYY-MM-DD",
            "startTime": "HH:MM",
            "dueTime": "HH:MM",
            "labels": "Labels",
        },
        ["task"],
    ),
    (
        "move_task",
        "Move a task to backlog, todo, doing or done.",
        {"task": "Task id or key", "status": "Status"},
        ["task", "status"],
    ),
    (
        "add_comment",
        "Comment on a task.",
        {"task": "Task id or key", "body": "Comment text"},
        ["task", "body"],
    ),
    (
        "list_epics",
        "List a project's epics with progress (done/total).",
        {"projectId": "Project id or key"},
        ["projectId"],
    ),
    (
        "create_epic",
        "Create an epic in a project.",
        {
            "projectId": "Project id or key",
            "title": "Title",
            "description": "Description",
            "priority": "Priority",
            "dueDate": "YYYY-MM-DD",
        },
        ["projectId", "title"],
    ),
    (
        "assign_task",
        "Set the assignees of a task (replaces the current list).",
        {"task": "Task id or key", "assigneeIds": "User ids"},
        ["task", "assigneeIds"],
    ),
    (
        "list_reminders",
        (
            "List reminders I can see (birthdays, anniversaries, tablets, events) "
            "with their next occurrence, soonest first."
        ),
        {},
        [],
    ),
    (
        "my_due_reminders",
        (
            "Reminders for me that are missed or coming up within their notice "
            "period, with the occurrence key needed to mark one done."
        ),
        {},
        [],
    ),
    (
        "create_reminder",
        (
            "Create a reminder. With no forIds and no groupIds it is just for me. "
            "Birthdays and anniversaries repeat yearly from date (date of birth or "
            "wedding date). Tablets: repeat daily with times and an endDate for a "
            "course."
        ),
        {
            "kind": "Kind",
            "title": "What, or whose birthday/anniversary",
            "date": "First day, YYYY-MM-DD",
            "yearKnown": "False when the year is unknown",
            "times": "HH:MM times of day",
            "repeat": "Repeat",
            "endDate": "Last day YYYY-MM-DD",
            "noticeDays": "Start warning this many days before",
            "forIds": "User ids it is for",
            "groupIds": "Group ids it is for",
            "notes": "Notes",
        },
        ["title", "date"],
    ),
    (
        "mark_reminder_done",
        (
            "Mark one occurrence of a reminder done, e.g. a tablet dose. occurrence"
            " is YYYY-MM-DD or YYYY-MM-DDTHH:MM from my_due_reminders."
        ),
        {"reminderId": "Reminder id", "occurrence": "Occurrence key", "done": "Done"},
        ["reminderId", "occurrence"],
    ),
    (
        "add_checklist_items",
        (
            "Add items to a task's checklist, such as a shopping list. Returns the "
            "whole checklist with item ids."
        ),
        {
            "task": "Task id or key",
            "items": 'One entry per item, e.g. ["Milk 2L", "Eggs"]',
        },
        ["task", "items"],
    ),
    (
        "tick_checklist_item",
        (
            "Tick or untick one checklist item. Item ids come from get_task or "
            "add_checklist_items."
        ),
        {"task": "Task id or key", "itemId": "Item id", "done": "Done"},
        ["task", "itemId"],
    ),
]


def plan_tool(
    name: str, description: str, properties: dict[str, str], required: list[str]
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": {
                key: {"type": "string", "description": text}
                for key, text in properties.items()
            },
            "required": required,
        },
    )


class FixturePlanClient:
    async def list_tools(self) -> SimpleNamespace:
        tools = [plan_tool(*entry) for entry in PLAN_TOOL_FIXTURE]
        return SimpleNamespace(tools=tools)


async def connect_fixture_plan(self: MCPToolbox, spec: Any) -> Any:
    if isinstance(spec, RemoteServer):
        return FixturePlanClient()
    return await ORIGINAL_OPEN(self, spec)


ORIGINAL_OPEN = MCPToolbox._open
MCPToolbox._open = connect_fixture_plan


def openai_payload(
    name: str, description: str, input_schema: dict[str, Any]
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": input_schema,
        },
    }


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


async def main() -> None:
    settings = Settings(_env_file=None, plan_mcp_token=FAKE_PLAN_TOKEN)
    toolbox = MCPToolbox(configured_servers(settings), settings.exposed_tools)
    await toolbox.connect()
    try:
        tools = toolbox.tools
    finally:
        await toolbox.aclose()

    rows = [
        (
            tool.name,
            estimate_tokens(
                json.dumps(
                    openai_payload(tool.name, tool.description, tool.input_schema)
                )
            ),
        )
        for tool in tools
    ]
    tool_total = sum(tokens for _, tokens in rows)
    system_tokens = estimate_tokens(SYSTEM_PROMPT)

    for name, tokens in rows:
        print(f"{tokens:6d}  {name}")
    print(f"tools:   {len(rows)} tools, about {tool_total} tokens")
    print(f"system:  about {system_tokens} tokens ({len(SYSTEM_PROMPT)} chars)")
    print(f"total:   about {tool_total + system_tokens} tokens")


if __name__ == "__main__":
    asyncio.run(main())
