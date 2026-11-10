"""Ontología exportada por Auto Ontology (formato nativo) como estructura de consulta.

Cada término apunta, por ID, a las tablas que representa y a las columnas que
describe. Aquí se resuelven esos IDs a nombres físicos (``esquema.tabla`` y
``esquema.tabla.columna``), que es lo que necesita quien escribe SQL.

Encima se aplica la capa de correcciones humanas (``correcciones.yaml``). Sus
llaves son nombres físicos, no los IDs del modelo: los IDs cambian en cada
compilación y los nombres de vistas y columnas no. Una corrección cuya vista o
columna ya no existe queda como huérfana y la ontología deja de estar
certificada hasta que alguien la revise.
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
    synonyms: list[str] = field(default_factory=list)
    corrected: bool = False  # True si la capa de correcciones tocó el término

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "synonyms": list(self.synonyms),
            "corrected": self.corrected,
            "tables": list(self.tables),
            "columns": [
                {"name": c.name, "description": c.description, "column": c.column, "type": c.type}
                for c in self.columns
            ],
        }


@dataclass(frozen=True)
class Relation:
    source: str  # esquema.tabla.columna
    target: str  # esquema.tabla.columna
    kind: str  # muchos_a_uno, uno_a_uno
    description: str = ""

    def as_dict(self) -> dict:
        return {"from": self.source, "to": self.target, "kind": self.kind, "description": self.description}


@dataclass(frozen=True)
class Measure:
    name: str
    table: str  # esquema.tabla
    sql: str  # expresión de agregación sobre columnas de ``table``
    description: str = ""
    unit: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "table": self.table,
            "sql": self.sql,
            "description": self.description,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class Corrections:
    applied: int = 0
    orphans: list[str] = field(default_factory=list)
    reviewed_by: str = ""
    certified: bool = False  # lo que declaró quien revisó

    def as_dict(self) -> dict:
        return {
            "applied": self.applied,
            "orphans": list(self.orphans),
            "reviewed_by": self.reviewed_by,
        }


@dataclass(frozen=True)
class Ontology:
    terms: list[Term]
    version: str  # primeros 12 caracteres del sha256 de la exportación y las correcciones
    relations: list[Relation] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)
    corrections: Corrections = field(default_factory=Corrections)
    source: str = "auto-ontology-agno"

    @property
    def certified(self) -> bool:
        """Certificada solo si alguien lo declaró y ninguna corrección quedó huérfana."""
        return self.corrections.certified and not self.corrections.orphans

    def term(self, name: str) -> Term | None:
        wanted = normalize(name)
        return next(
            (t for t in self.terms if wanted in {normalize(t.name), *map(normalize, t.synonyms)}),
            None,
        )

    def related(self, term: Term) -> dict:
        tables = set(term.tables)
        return {
            "relations": [
                r.as_dict()
                for r in self.relations
                if r.source.rsplit(".", 1)[0] in tables or r.target.rsplit(".", 1)[0] in tables
            ],
            "measures": [m.as_dict() for m in self.measures if m.table in tables],
        }

    def summary(self) -> dict:
        return {
            "version": self.version,
            "certified": self.certified,
            "terms": len(self.terms),
            "source": self.source,
            "corrections": self.corrections.as_dict(),
        }


def _parse_export(document: dict) -> tuple[list[Term], set[str]]:
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
    known = set(tables.values()) | {physical for physical, _ in columns.values()}
    return terms, known


def _apply(terms: list[Term], known: set[str], fixes: dict) -> tuple[list[Term], list, list, Corrections]:
    orphans: list[str] = []
    applied = 0
    by_table = {table: index for index, term in enumerate(terms) for table in term.tables}

    for table, change in (fixes.get("terminos") or {}).items():
        if table not in by_table:
            orphans.append(f"terminos.{table}")
            continue
        index = by_table[table]
        term = terms[index]
        column_fixes = change.get("columnas") or {}
        for column in column_fixes:
            if not any(c.column == column for c in term.columns):
                orphans.append(f"terminos.{table}.columnas.{column}")
        new_columns = []
        for column in term.columns:
            fix = column_fixes.get(column.column) or {}
            new_columns.append(
                TermColumn(
                    name=fix.get("nombre", column.name),
                    description=fix.get("descripcion", column.description),
                    column=column.column,
                    type=column.type,
                )
            )
            applied += bool(fix)
        terms[index] = Term(
            id=term.id,
            name=change.get("nombre", term.name),
            description=change.get("descripcion", term.description),
            tables=term.tables,
            columns=new_columns,
            synonyms=list(change.get("sinonimos") or term.synonyms),
            corrected=True,
        )
        applied += 1

    relations = []
    for item in fixes.get("relaciones") or []:
        missing = [end for end in (item["desde"], item["hacia"]) if end not in known]
        if missing:
            orphans.append(f"relaciones.{item['desde']}->{item['hacia']}")
            continue
        relations.append(
            Relation(
                item["desde"], item["hacia"], item.get("tipo", "muchos_a_uno"), item.get("descripcion", "")
            )
        )
        applied += 1

    measures = []
    for item in fixes.get("medidas") or []:
        if item["vista"] not in known:
            orphans.append(f"medidas.{item['nombre']}")
            continue
        measures.append(
            Measure(
                item["nombre"],
                item["vista"],
                item["sql"],
                item.get("descripcion", ""),
                item.get("unidad", ""),
            )
        )
        applied += 1

    corrections = Corrections(
        applied=applied,
        orphans=orphans,
        reviewed_by=str(fixes.get("revisado_por") or ""),
        certified=bool(fixes.get("certificada", False)),
    )
    return terms, relations, measures, corrections


def load_ontology(path: Path, corrections: Path | None = None) -> Ontology:
    """Carga la exportación nativa y, si existe, la capa de correcciones humanas.

    La certificación la declara quien revisó, dentro de ``correcciones.yaml``;
    la exportación del modelo por sí sola nunca está certificada.
    """
    raw = Path(path).read_bytes()
    terms, known = _parse_export(yaml.safe_load(raw) or {})
    digest = hashlib.sha256(raw)
    relations: list[Relation] = []
    measures: list[Measure] = []
    summary = Corrections()
    if corrections is not None and Path(corrections).exists():
        fixes_raw = Path(corrections).read_bytes()
        digest.update(fixes_raw)
        terms, relations, measures, summary = _apply(terms, known, yaml.safe_load(fixes_raw) or {})
    return Ontology(
        terms=terms,
        version=digest.hexdigest()[:12],
        relations=relations,
        measures=measures,
        corrections=summary,
    )
