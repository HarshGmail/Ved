DOMAIN_SEPARATOR = "."
DEFAULT_ACKNOWLEDGEMENT = "On it…"

ACKNOWLEDGEMENTS: dict[str, str] = {
    "reminders": "Setting that up…",
    "reminders.list": "Let me check your reminders…",
    "people": "Noting that down…",
    "people.list": "Let me check…",
    "memory.search": "Let me look back…",
    "documents": "Let me check your documents…",
    "web": "Let me check that…",
}


def acknowledgement_for(tool_name: str) -> str:
    domain = tool_name.split(DOMAIN_SEPARATOR, 1)[0]
    return ACKNOWLEDGEMENTS.get(
        tool_name, ACKNOWLEDGEMENTS.get(domain, DEFAULT_ACKNOWLEDGEMENT)
    )
