
from dataclasses import dataclass
from typing import Any


class CATIAConnectionError(RuntimeError):
    """Erreur de connexion ou d'accès à CATIA V5."""


@dataclass
class CATIASession:
    application: Any
    document: Any
    document_name: str
    document_type: str


def connect_to_catia() -> CATIASession:
    """
    Connecte Python à une instance CATIA V5 déjà ouverte.
    Ne démarre pas CATIA et ne modifie pas le document.
    """
    try:
        import win32com.client
    except ImportError as exc:
        raise CATIAConnectionError(
            "pywin32 n'est pas installé."
        ) from exc

    try:
        catia = win32com.client.GetActiveObject(
            "CATIA.Application"
        )
    except Exception as exc:
        raise CATIAConnectionError(
            "CATIA V5 n'est pas ouvert ou non accessible via COM."
        ) from exc

    try:
        document = catia.ActiveDocument
        document_name = str(document.Name)
        document_type = document_name.rsplit(".", 1)[-1]

        if document_type.lower() == "catpart":
            document_type = "Part"
        elif document_type.lower() == "catproduct":
            document_type = "Product"
        elif document_type.lower() == "catdrawing":
            document_type = "Drawing"
        else:
            document_type = "Unknown"
    except Exception as exc:
        raise CATIAConnectionError(
            "Aucun document CATIA actif accessible."
        ) from exc

    return CATIASession(
        application=catia,
        document=document,
        document_name=document_name,
        document_type=document_type,
    )
