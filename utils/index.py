import os
from typing import Optional
from twelvelabs.types.index_schema import IndexSchema
from twelvelabs.indexes.types.indexes_create_request_models_item import IndexesCreateRequestModelsItem
from .tl_client import get_client

INDEX_NAME = os.environ.get("TL_INDEX_NAME", "fieldlens-atlas")


def get_or_create_index() -> IndexSchema:
    """Return the FieldLens Marengo index, creating it if it doesn't exist."""
    client = get_client()

    for idx in client.indexes.list(index_name=INDEX_NAME):
        return idx

    return client.indexes.create(
        index_name=INDEX_NAME,
        models=[
            IndexesCreateRequestModelsItem(
                model_name="marengo3.0",
                model_options=["visual", "audio"],
            )
        ],
    )
