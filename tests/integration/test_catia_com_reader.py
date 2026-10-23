
import unittest

from catia_extractor.catia.connection import connect_to_catia
from catia_extractor.catia.com_reader import read_catia_part


class TestCATIAComReader(unittest.TestCase):

    def test_read_active_part(self):
        session = connect_to_catia()
        result = read_catia_part(session)

        print("\n--- CATIA COM READER ---")
        print("Document :", result.document_name)
        print("Part :", result.part_name)
        print("Parameters :", len(result.parameters))
        print("Bodies :", len(result.features))

        print("\n--- FIRST PARAMETERS ---")
        for param in result.parameters[:10]:
            print(param)

        print("\n--- BODIES ---")
        for feature in result.features:
            print(feature)

        print("\n--- WARNINGS ---")
        for warning in result.warnings:
            print(warning)

        self.assertTrue(result.part_name)
        self.assertEqual(
            result.document_name,
            session.document_name
        )


if __name__ == "__main__":
    unittest.main()
