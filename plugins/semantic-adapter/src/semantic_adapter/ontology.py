"""Ontología exportada por Auto Ontology (formato nativo) como estructura de consulta.

Cada término apunta, por ID, a las tablas que representa y a las columnas que
describe. Aquí se resuelven esos IDs a nombres físicos (``esquema.tabla`` y
``esquema.tabla.columna``), que es lo que necesita quien escribe SQL.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def normalize(text: str) -> str:
    """Minúsculas, sin acentos y con espacios simples, para comparar nombres."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


@dataclass(frozen=True)
class TermColumn:
    name: str
    description: str
    column: str  # esquema.tabla.columna
    type: str = ""


@dataclass(frozen=True)
class Term:
    id: str
    name: str
    description: str
    tables: list[str] = field(default_factory=list)  # esquema.tabla
    columns: list[TermColumn] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "tables": list(self.tables),
            "columns": [
                {"name": c.name, "description": c.description, "column": c.column, "type": c.type}
                for c in self.columns
            ],
        }


@dataclass(frozen=True)
class Ontology:
    terms: list[Term]
    version: str  # primeros 12 caracteres del sha256 del archivo
    certified: bool = False
    source: str = "auto-ontology-agno"

    def term(self, name: str) -> Term | None:
        wanted = normalize(name)
        return next((t for t in self.terms if normalize(t.name) == wanted), None)

    def summary(self) -> dict:
        return {
            "version": self.version,
            "certified": self.certified,
            "terms": len(self.terms),
            "source": self.source,
        }


def load_ontology(path: Path, certified: bool = False) -> Ontology:
    """Carga el YAML nativo. ``certified`` lo decide quien revisó, no el archivo."""
    raw = Path(path).read_bytes()
    document = yaml.safe_load(raw) or {}

    tables: dict[str, str] = {}
    columns: dict[str, tuple[str, str]] = {}
    for database in document.get("data_layer", {}).get("databases", []) or []:
        for schema in database.get("schemas", []) or []:
            for table in schema.get("tables", []) or []:
                qualified = f"{schema['name']}.{table['name']}"
                tables[table["id"]] = qualified
                for column in table.get("columns", []) or []:
                    columns[column["id"]] = (f"{qualified}.{column['name']}", column.get("type", ""))

    terms = []
    for item in document.get("semantic_layer", {}).get("terms", []) or []:
        term_columns = []
        for attribute in item.get("columns_attributes", []) or []:
            physical, kind = columns.get(attribute.get("column_id"), ("", ""))
            if physical:
                term_columns.append(
                    TermColumn(
                        name=attribute.get("name", ""),
                        description=attribute.get("description", "") or "",
                        column=physical,
                        type=kind,
                    )
                )
        terms.append(
            Term(
                id=item["id"],
                name=item.get("name", ""),
                description=item.get("description", "") or "",
                tables=[tables[t] for t in item.get("represents", []) or [] if t in tables],
                columns=term_columns,
            )
        )

    return Ontology(
        terms=terms,
        version=hashlib.sha256(raw).hexdigest()[:12],
        certified=certified,
    )
