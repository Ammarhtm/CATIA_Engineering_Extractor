from catia_extractor.catia.connection import connect_to_catia


def test_pipeline_connection():
    session = connect_to_catia()

    assert session is not None, "CATIA session is None"

    document = session.document

    assert document is not None, "No active CATIA document"

    document_name = document.Name

    assert document_name, "Document name is empty"

    part = document.Part

    assert part is not None, "Document has no accessible Part"

    print("\n====== PIPELINE V1 CONNECTION ======")
    print("Document:", document_name)
    print("Part accessible:", part is not None)
    print("Connection status: SUCCESS")
