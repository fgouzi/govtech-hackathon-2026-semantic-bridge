class SemanticBridgeError(Exception):
    """Base exception for all semantic-bridge errors."""


class MCPConnectionError(SemanticBridgeError):
    """Raised when MCP server connection fails."""


class MCPProtocolError(SemanticBridgeError):
    """Raised on malformed JSON-RPC messages."""


class SemanticMatchError(SemanticBridgeError):
    """Raised when semantic matching fails."""


class EmbeddingError(SemanticBridgeError):
    """Raised on embedding model failures."""


class TransformationError(SemanticBridgeError):
    """Raised when a transformation cannot be applied."""


class ValidationError(SemanticBridgeError):
    """Raised when validation detects fatal errors."""


class AgentError(SemanticBridgeError):
    """Raised on LLM agent failures."""


class CacheError(SemanticBridgeError):
    """Raised on SQLite cache failures."""


class ClosedDatasetError(SemanticBridgeError):
    """Raised when a dataset has no public distribution and cannot be accessed."""

    def __init__(self, dataset_id: str, reason: str = "No public distribution available") -> None:
        self.dataset_id = dataset_id
        self.reason = reason
        super().__init__(f"Dataset '{dataset_id}' is not publicly accessible: {reason}")

