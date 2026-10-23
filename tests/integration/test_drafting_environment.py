
from catia_extractor.catia.connection import connect_to_catia


def test_drafting_environment():
    session = connect_to_catia()

    # Access to the CATIA application
    app = session.document.Application

    print("\n====== CATIA DOCUMENTS ======")

    documents = app.Documents
    print("Open documents:", documents.Count)

    drawing_count = 0

    for i in range(1, documents.Count + 1):
        doc = documents.Item(i)

        print(
            "Document:",
            doc.Name,
        )

        if doc.Name.lower().endswith(".catdrawing"):
            drawing_count += 1

            try:
                sheets = doc.Sheets
                print("  Sheets:", sheets.Count)

                for j in range(1, sheets.Count + 1):
                    sheet = sheets.Item(j)
                    print("  Sheet:", sheet.Name)

                    views = sheet.Views
                    print("  Views:", views.Count)

                    for k in range(1, views.Count + 1):
                        view = views.Item(k)
                        print("    View:", view.Name)

            except Exception as exc:
                print("  Inspection error:", repr(exc))

    print("CATDrawings found:", drawing_count)
