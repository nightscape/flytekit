"""
Logic for serializing a basemodel to a literalmap that can be passed between container

The serialization process is as follows:

1. Serialize the basemodel to json, replacing all flyte types with unique placeholder strings
2. Serialize the flyte types to separate literals and store them in the flyte object store (a singleton object)
3. Return a literal map with the json and the flyte object store represented as a literalmap {placeholder: flyte type}

"""
from typing import Any, Dict, NamedTuple, Union, cast
from typing_extensions import Annotated
import uuid

import pydantic
from google.protobuf import struct_pb2

from flytekit.models import literals
from flytekit.core import context_manager, type_engine

from . import commons


BASEMODEL_JSON_KEY = "BaseModel JSON"
FLYTETYPE_OBJSTORE__KEY = "Flyte Object Store"

SerializedBaseModel = Annotated[str, "A pydantic BaseModel that has been serialized with placeholders for Flyte types."]

ObjectStoreID = Annotated[str, "Key for unique literalmap of a serialized basemodel."]
LiteralObjID = Annotated[str, "Key for unique object in literal map."]
LiteralStore = Annotated[Dict[LiteralObjID, literals.Literal], "uid to literals for a serialized BaseModel"]


class BaseModelFlyteObjectStore:
    """
    This class is an intermediate store for python objects that are being serialized/deserialized.

    On serialization of a basemodel, flyte objects are serialized and stored in this object store.
    """

    def __init__(self) -> None:
        self.literal_store: LiteralStore = dict()

    def register_python_object(self, python_object: object) -> LiteralObjID:
        """Serialize to literal and return a unique identifier."""
        serialized_item = serialize_to_flyte_literal(python_object)
        identifier = make_identifier_for_serializeable(python_object)
        self.literal_store[identifier] = serialized_item
        return identifier

    def as_literalmap(self) -> literals.LiteralMap:
        """
        Converts the object store to a literal map
        """
        return literals.LiteralMap(literals=self.literal_store)


def serialize_basemodel(basemodel: pydantic.BaseModel) -> literals.LiteralMap:
    """
    Serializes a given pydantic BaseModel instance into a LiteralMap.
    The BaseModel is first serialized into a JSON format, where all Flyte types are replaced with unique placeholder strings.
    The Flyte Types are serialized into separate Flyte literals
    """
    store = BaseModelFlyteObjectStore()
    basemodel_literal = serialize_basemodel_to_literal(basemodel, store)
    store_literal = store.as_literalmap()
    return literals.LiteralMap(
        {
            BASEMODEL_JSON_KEY: basemodel_literal,  # json with flyte types replaced with placeholders
            FLYTETYPE_OBJSTORE__KEY: store_literal,  # placeholders mapped to flyte types
        }
    )


def serialize_basemodel_to_literal(
    basemodel: pydantic.BaseModel,
    flyteobject_store: BaseModelFlyteObjectStore,
) -> literals.Literal:
    """ """
    basemodel_json = serialize_basemodel_to_json_and_store(basemodel, flyteobject_store)
    basemodel_literal = make_literal_from_json(basemodel_json)
    return basemodel_literal


def make_literal_from_json(json: str) -> literals.Literal:
    """
    Converts the json representation of a pydantic BaseModel to a Flyte Literal.
    """
    # serialize as a string literal
    ctx = context_manager.FlyteContext.current_context()
    string_transformer = type_engine.TypeEngine.get_transformer(json)
    return string_transformer.to_literal(ctx, json, str, string_transformer.get_literal_type(str))


def serialize_basemodel_to_json_and_store(
    basemodel: pydantic.BaseModel,
    flyteobject_store: BaseModelFlyteObjectStore,
) -> SerializedBaseModel:
    """
    Serialize a pydantic BaseModel to json and protobuf, separating out the Flyte types into a separate store.
    On deserialization, the store is used to reconstruct the Flyte types.
    """

    def encoder(obj: Any) -> Union[str, commons.LiteralObjID]:
        if isinstance(obj, commons.PYDANTIC_SUPPORTED_FLYTE_TYPES):
            return flyteobject_store.register_python_object(obj)
        return basemodel.__json_encoder__(obj)

    return basemodel.json(encoder=encoder)


def serialize_to_flyte_literal(python_obj: object) -> literals.Literal:
    """
    Use the Flyte TypeEngine to serialize a python object to a Flyte Literal.
    """
    python_type = type(python_obj)
    ctx = context_manager.FlyteContextManager().current_context()
    literal_type = type_engine.TypeEngine.to_literal_type(python_type)
    literal_obj = type_engine.TypeEngine.to_literal(ctx, python_obj, python_type, literal_type)
    return literal_obj


def make_identifier_for_serializeable(python_type: object) -> LiteralObjID:
    """
    Create a unique identifier for a python object.
    """
    unique_id = f"{type(python_type).__name__}_{uuid.uuid4().hex}"
    return cast(LiteralObjID, unique_id)
