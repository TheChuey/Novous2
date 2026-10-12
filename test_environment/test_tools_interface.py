import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from core_engine import tool_catalog
from server import app
from tools import interface


class TestToolsInterface(unittest.TestCase):
    def setUp(self):
        tool_catalog.load_tools(reload=True)

    def tearDown(self):
        tool_catalog.load_tools(reload=True)

    def test_register_get_remove_round_trip(self):
        source = (
            "def calc_square(n: int) -> int:\n"
            "    \"\"\"Calculate square of n.\"\"\"\n"
            "    return n * n\n"
        )
        with tempfile.TemporaryDirectory() as td:
            promoted_path = Path(td) / "promoted.py"
            header = (
                '"""Custom tools promoted from the Function Testing Workbench."""\n'
                'from core_engine.tool_catalog import tool\n\n'
                '# PROMOTION_MARKER: tools appended below will be registered as custom tools\n\n'
            )
            promoted_path.write_text(header, encoding="utf-8", newline="\n")
            initial_bytes = promoted_path.read_bytes()

            with patch("tools.interface.PROMOTED_MODULE_PATH", promoted_path):
                # 1. Register
                reg_result = interface.register_tool(source, "calc_square")
                self.assertEqual(reg_result["name"], "calc_square")
                self.assertEqual(reg_result["path"], "tools/promoted.py")

                # 2. Get tool callable
                fn = interface.get_tool("calc_square")
                self.assertIsNotNone(fn)
                self.assertEqual(fn(5), 25)

                # 3. Get tool source
                src_info = interface.get_tool_source("calc_square")
                self.assertEqual(src_info["name"], "calc_square")
                self.assertIn("calc_square", src_info["source"])
                self.assertEqual(src_info["path"], "tools/promoted.py")

                # 4. Remove tool
                del_result = interface.remove_tool("calc_square")
                self.assertTrue(del_result["deleted"])
                self.assertIsNone(interface.get_tool("calc_square"))

                # 5. Check byte-identical
                after_bytes = promoted_path.read_bytes()
                self.assertEqual(initial_bytes, after_bytes)

    def test_router_endpoints(self):
        client = TestClient(app)

        # GET /api/tools
        resp = client.get("/api/tools")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tools", data)
        self.assertIn("providers", data)
        self.assertIn("warnings", data)
        self.assertIn("calculator", [t["name"] for t in data["tools"]])

        # GET /api/tools/calculator
        resp = client.get("/api/tools/calculator")
        self.assertEqual(resp.status_code, 200)
        calc_data = resp.json()
        self.assertEqual(calc_data["name"], "calculator")
        self.assertEqual(calc_data["provider"], "core_engine")

        # GET /api/tools/health
        resp = client.get("/api/tools/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "healthy")

        with tempfile.TemporaryDirectory() as td:
            promoted_path = Path(td) / "promoted.py"
            with patch("tools.interface.PROMOTED_MODULE_PATH", promoted_path):
                # POST /api/tools/register
                tool_code = "def custom_api_test(x: int) -> int:\n    return x + 10\n"
                reg_resp = client.post(
                    "/api/tools/register",
                    json={"source": tool_code, "name": "custom_api_test"},
                )
                self.assertEqual(reg_resp.status_code, 200)
                self.assertEqual(reg_resp.json()["name"], "custom_api_test")

                # GET /api/tools/{name}
                get_resp = client.get("/api/tools/custom_api_test")
                self.assertEqual(get_resp.status_code, 200)
                self.assertTrue(get_resp.json()["custom"])

                # DELETE /api/tools/{name}
                del_resp = client.delete("/api/tools/custom_api_test")
                self.assertEqual(del_resp.status_code, 200)

                # GET after delete -> 404
                get_after = client.get("/api/tools/custom_api_test")
                self.assertEqual(get_after.status_code, 404)


if __name__ == "__main__":
    unittest.main()
