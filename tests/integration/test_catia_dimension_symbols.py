
import unittest

from catia_extractor.catia.connection import connect_to_catia


def probe(label, callback):
    try:
        value = callback()
        print(f"  {label}: {value!r}")
        return value
    except Exception as exc:
        print(
            f"  {label}: ERROR "
            f"{type(exc).__name__}: {exc}"
        )
        return None


class TestDimensionSymbols(unittest.TestCase):

    def test_dimensions(self):
        session = connect_to_catia()
        sets = session.document.Part.AnnotationSets

        found = 0

        for si in range(1, sets.Count + 1):
            annotations = sets.Item(si).Annotations

            for i in range(1, annotations.Count + 1):
                ann = annotations.Item(i)

                if str(ann.Type) != "FTA_LinearDimension":
                    continue

                found += 1
                print(f"\n===== {ann.Name} =====")

                has_limit = probe(
                    "HasDimensionLimit",
                    lambda: ann.HasDimensionLimit()
                )

                envelope = probe(
                    "HasAnEnvelopCondition",
                    lambda: ann.HasAnEnvelopCondition()
                )

                if has_limit is True:
                    limit = probe(
                        "DimensionLimit",
                        lambda: ann.DimensionLimit()
                    )

                    if limit is not None:
                        nominal = probe(
                            "Nominalvalue",
                            lambda: limit.Nominalvalue
                        )

                        limit_type = probe(
                            "DimensionLimitType",
                            lambda: limit.DimensionLimitType
                        )

                        symmetric = probe(
                            "SymetricValue",
                            lambda: limit.SymetricValue
                        )

                        bounds = probe(
                            "Limits (bottom, upper)",
                            lambda: limit.Limits()
                        )

                        if (
                            isinstance(bounds, (tuple, list))
                            and len(bounds) == 2
                        ):
                            bottom, upper = bounds
                            print("  Bottom deviation:", bottom)
                            print("  Upper deviation:", upper)
                        elif bounds is not None:
                            print(
                                "  Returned data requires inspection:",
                                repr(bounds)
                            )

        self.assertEqual(found, 3)


if __name__ == "__main__":
    unittest.main()
