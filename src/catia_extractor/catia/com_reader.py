
from dataclasses import dataclass, field
from typing import Any

from catia_extractor.catia.connection import CATIASession


@dataclass
class COMReadResult:
    document_name: str
    part_name: str = ""
    parameters: list[dict[str, Any]] = field(default_factory=list)
    features: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def read_catia_part(session: CATIASession) -> COMReadResult:
    """Lecture seule des données accessibles d'un CATPart."""

    result = COMReadResult(document_name=session.document_name)

    if session.document_type != "Part":
        result.warnings.append(
            "Document non CATPart : extraction ignorée."
        )
        return result

    try:
        part = session.document.Part
        result.part_name = str(part.Name)
    except Exception as exc:
        result.warnings.append(f"Accès à Part impossible : {exc}")
        return result

    # Paramètres CATIA
    try:
        parameters = part.Parameters

        for i in range(1, parameters.Count + 1):
            parameter = parameters.Item(i)

            try:
                value = str(parameter.ValueAsString())
            except Exception:
                try:
                    value = str(parameter.Value)
                except Exception:
                    value = None

            result.parameters.append({
                "name": str(parameter.Name),
                "value": value,
            })

    except Exception as exc:
        result.warnings.append(f"Paramètres : {exc}")

    # Fonctions principales de la pièce
    try:
        bodies = part.Bodies

        for i in range(1, bodies.Count + 1):
            body = bodies.Item(i)

            result.features.append({
                "name": str(body.Name),
                "category": "Body",
            })

    except Exception as exc:
        result.warnings.append(f"Bodies : {exc}")

    return result
