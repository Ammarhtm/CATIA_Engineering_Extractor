
import unittest

from catia_extractor.catia.connection import (
    CATIAConnectionError,
    connect_to_catia,
)


class TestCATIAConnection(unittest.TestCase):

    def test_connect_to_running_catia(self):
        try:
            session = connect_to_catia()
        except CATIAConnectionError as exc:
            self.fail(f"Connexion CATIA échouée : {exc}")

        print("\n--- CATIA CONNECTION ---")
        print("Document :", session.document_name)
        print("Type     :", session.document_type)

        self.assertTrue(session.document_name)
        self.assertTrue(session.document_type)
        self.assertIsNotNone(session.document)


if __name__ == "__main__":
    unittest.main()
