"""Bounded directed, single-commodity integer-capacity network inputs."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

MAX_BYTES = 200_000
NAME = re.compile(r"[A-Za-z0-9_.:-]{1,100}\Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("non-finite JSON constant")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def read_json(path, limit=MAX_BYTES):
    with Path(path).open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("JSON input exceeds byte limit")
    return strict_json(raw.decode("utf-8"))


def name(value):
    return type(value) is str and NAME.fullmatch(value) is not None


@dataclass(frozen=True)
class Network:
    encoded: str

    @classmethod
    def from_document(cls, document):
        if type(document) is not dict or set(document) != {
            "version",
            "nodes",
            "links",
            "source",
            "sink",
            "demand",
        }:
            raise ValueError("network needs exactly version/nodes/links/source/sink/demand")
        if type(document["version"]) is not int or document["version"] != 1:
            raise ValueError("version must be integer 1")
        nodes = document["nodes"]
        if (
            type(nodes) is not list
            or not 2 <= len(nodes) <= 30
            or any(not name(node) for node in nodes)
            or len(set(nodes)) != len(nodes)
        ):
            raise ValueError("need 2-30 distinct valid node IDs")
        source, sink = document["source"], document["sink"]
        if (
            not name(source)
            or not name(sink)
            or source not in nodes
            or sink not in nodes
            or source == sink
        ):
            raise ValueError("source and sink must be distinct listed nodes")
        demand = document["demand"]
        if type(demand) is not int or not 0 <= demand <= 10**12:
            raise ValueError("demand must be integer 0-1000000000000")
        links = document["links"]
        if type(links) is not list or len(links) > 80:
            raise ValueError("at most 80 directed links are supported")
        ids = set()
        for link in links:
            if type(link) is not dict or set(link) != {"id", "from", "to", "capacity"}:
                raise ValueError("each link needs exactly id/from/to/capacity")
            if not name(link["id"]) or link["id"] in ids:
                raise ValueError("link IDs must be valid and unique")
            ids.add(link["id"])
            if (
                not name(link["from"])
                or not name(link["to"])
                or link["from"] not in nodes
                or link["to"] not in nodes
                or link["from"] == link["to"]
            ):
                raise ValueError(
                    "links need listed, distinct endpoints; self-loops are unsupported"
                )
            if type(link["capacity"]) is not int or not 0 <= link["capacity"] <= 10**9:
                raise ValueError("capacity must be integer 0-1000000000")
        normalized = dict(
            version=1,
            nodes=sorted(nodes),
            links=sorted(links, key=lambda row: row["id"]),
            source=source,
            sink=sink,
            demand=demand,
        )
        encoded = canonical(normalized)
        if len(encoded.encode()) > MAX_BYTES:
            raise ValueError("normalized network exceeds byte limit")
        return cls(encoded)

    @classmethod
    def load(cls, path):
        return cls.from_document(read_json(path))

    def document(self):
        return json.loads(self.encoded)

    @property
    def sha256(self):
        return hashlib.sha256(self.encoded.encode()).hexdigest()
