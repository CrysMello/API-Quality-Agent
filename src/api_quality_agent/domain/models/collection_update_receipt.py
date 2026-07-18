from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionUpdateReceipt:
    confirmed_collection_id: str
    status_code: int
    request_id: str | None
    document_hash: str
