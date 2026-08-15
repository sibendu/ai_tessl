import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("oracle_spec_inventory.py")
SPEC = importlib.util.spec_from_file_location("oracle_spec_inventory", SCRIPT)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)


class OracleSpecInventoryTests(unittest.TestCase):
    def test_double_escaped_forms_text_does_not_truncate_select(self) -> None:
        code = "select '1'&amp;#10; from GLA_DISCOUNTING_SCHEMES DCS&amp;#10; where DCS.CTT_ID = 1;"
        self.assertIn("GLA_DISCOUNTING_SCHEMES", inventory.extract_sql_object_references(code))

    def test_namespaced_form_and_nested_ddl_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            form_dir = root / "form"
            ddl_dir = root / "ddl" / "views"
            ui_dir = root / "ui"
            form_dir.mkdir(parents=True)
            ddl_dir.mkdir(parents=True)
            ui_dir.mkdir(parents=True)

            (form_dir / "sample.fmb").write_bytes(b"binary")
            (form_dir / "sample_fmb.xml").write_text(
                """<?xml version="1.0"?>
<f:Module xmlns:f="urn:forms">
  <f:FormModule f:Name="SAMPLE" f:Title="Sample Form">
    <f:AttachedLibrary f:Name="SAMPLEL"/>
    <f:ProgramUnit f:Name="CHECK_X" f:ProgramUnitText="select '1'&amp;amp;#10; from SAMPLE_VIEW;"/>
  </f:FormModule>
</f:Module>
""",
                encoding="utf-8",
            )
            (form_dir / "samplel.pll").write_bytes(b"binary")
            (ddl_dir / "sample_view.sql").write_text(
                "CREATE OR REPLACE VIEW SAMPLE_VIEW AS SELECT 1 ID FROM DUAL;\n",
                encoding="utf-8",
            )

            manifest = inventory.build_manifest(root, "SAMPLE")
            self.assertEqual(2, manifest["schema_version"])
            self.assertEqual(1, manifest["inventory"]["ddl_files"])
            self.assertEqual("Sample Form", manifest["modules"][0]["title"])
            self.assertIn("SAMPLE_VIEW", manifest["modules"][0]["referenced_sql_objects"])
            status = {item["name"]: item["status"] for item in manifest["modules"][0]["library_source_status"]}
            self.assertEqual("binary-only", status["samplel"])
            self.assertEqual(64, len(manifest["input_manifest_sha256"]))


if __name__ == "__main__":
    unittest.main()
