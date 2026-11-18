"""TODO: implement initial artifact data; introductory gameplay has no artifacts."""
from src.api import ArtifactDefinition, Position
 
 
class Artifact:
    """Expose read-only canonical identity, position, and nonnegative value."""
 
    def __init__(self, artifact_id: str, position: Position, value: int) -> None:
        # ArtifactDefinition checks all three values for us.
        self._data = ArtifactDefinition(artifact_id, position, value)
 
    @property
    def artifact_id(self) -> str:
        return self._data.artifact_id
 
    @property
    def position(self) -> Position:
        return self._data.position
 
    @property
    def value(self) -> int:
        return self._data.value
 