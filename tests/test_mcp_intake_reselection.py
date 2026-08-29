import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from photoloset import mcp
from photoloset.garment import Intake


class MCPIntakeReselectionTests(unittest.TestCase):
    def test_registering_existing_image_with_clip_remains_json_answer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image = root / "garment.png"
            image.write_bytes(b"not-an-image-decoder-test")
            intake = Intake()
            intake.register(str(image), "image", at="first")
            intake.add_clip(str(image), str(image), "still", 0.0)

            with patch.object(mcp, "_intake", return_value=intake), patch.object(
                mcp, "_p", return_value=root / "intake.json"
            ):
                answer = json.loads(mcp.intake_register(str(image), "image"))

        self.assertEqual(answer["verdict"], "ANSWER")
        self.assertEqual(answer["source"]["path"], str(image))
        self.assertEqual(answer["source"]["clips"], [{
            "path": str(image), "mark": "still", "seconds": 0.0
        }])


if __name__ == "__main__":
    unittest.main()
