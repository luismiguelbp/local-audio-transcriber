import tempfile
import unittest
from pathlib import Path

from local_audio_transcriber.transcriber import save_transcription


class SaveTranscriptionTests(unittest.TestCase):
    def test_save_transcription_creates_directory_and_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "nested" / "result.txt"
            saved = save_transcription("hello world", str(output_path))
            saved_path = Path(saved)

            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.read_text(encoding="utf-8"), "hello world")

    def test_save_transcription_forces_txt_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "result.md"
            saved = save_transcription("text", str(output_path))
            saved_path = Path(saved)

            self.assertEqual(saved_path.suffix, ".txt")
            self.assertTrue(saved_path.exists())


if __name__ == "__main__":
    unittest.main()
