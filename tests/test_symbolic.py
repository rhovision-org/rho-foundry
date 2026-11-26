import json
from pathlib import Path
import unittest

from foundry.core import SpecError, compile_protocol, manifest, rholang
from foundry.symbolic import compile_symbolic


ROOT = Path(__file__).resolve().parents[1]


def example(name):
    return json.loads((ROOT / "examples" / f"{name}.json").read_text())


class SymbolicCompilation(unittest.TestCase):
    def test_large_guarded_workflow_and_authorized_macro(self):
        spec = example("hold-quota")
        output, source = compile_symbolic(spec)
        self.assertEqual(compile_symbolic(spec), (output, source))
        self.assertEqual(output["initial"], [1_000_000, 0, 0])
        self.assertEqual(output["preservation"]["reserve"], ["inductive", "interval_bound"])
        self.assertEqual(output["macros"]["fill_quota"]["primitive"], "reserve")
        self.assertLess(len(source), 20_000)
        with self.assertRaisesRegex(SpecError, "state budget exceeded"):
            compile_protocol(spec)

    def test_unproved_invariant_is_rejected(self):
        spec = example("hold-quota")
        spec["actions"][0]["guards"] = []
        with self.assertRaisesRegex(SpecError, "reserve, invariant 2"):
            compile_symbolic(spec)

    def test_preserves_goal_authority_and_checks_supported_goal_shape(self):
        spec = example("hold-quota")
        spec["goals"][0]["actions"].append("issue")
        with self.assertRaisesRegex(SpecError, "escalate authority"):
            compile_symbolic(spec)
        spec["goals"][0]["actions"][1] = "release"
        with self.assertRaisesRegex(SpecError, "requires one primitive"):
            compile_symbolic(spec)
        spec["goals"][0]["actions"].pop()
        spec["goals"][0]["predicates"][0]["weights"]["held"] = 2
        with self.assertRaisesRegex(SpecError, "unit-rate equality"):
            compile_symbolic(spec)

    def test_single_pass_preserves_both_enumerated_artifacts(self):
        for name in ("escrow", "reservation"):
            spec = example(name)
            self.assertEqual(compile_protocol(spec), (manifest(spec), rholang(spec)))
