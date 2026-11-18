"""TODO: implement your character's immutable, canonical public identity."""
from src.api import CharacterDefinition


class Character:
    """Character(agent_id); expose a read-only str agent_id property."""

    def __init__(self, agent_id: str) -> None:
        # CharacterDefinition checks the id for us:
        # it must be a non-empty string with no spaces at the start or end.
        self._data = CharacterDefinition(agent_id)

    @property
    def agent_id(self) -> str:
        return self._data.agent_id