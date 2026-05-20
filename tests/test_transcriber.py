import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_audio_transcriber.transcriber import AudioTranscriber, save_transcription


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


class AudioTranscriberTests(unittest.TestCase):
    @patch("local_audio_transcriber.transcriber.OpenAI")
    def test_transcriber_uses_configured_model(self, openai_cls):
        fake_client = MagicMock()
        fake_client.audio.transcriptions.create.return_value = "ok"
        openai_cls.return_value = fake_client

        transcriber = AudioTranscriber("test-key", model="gpt-4o-transcribe")

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "sample.wav"
            audio_path.write_bytes(b"not-real-audio")
            result = transcriber._transcribe_single_file(str(audio_path))

        self.assertEqual(result, "ok")
        fake_client.audio.transcriptions.create.assert_called_once()
        self.assertEqual(
            fake_client.audio.transcriptions.create.call_args.kwargs["model"],
            "gpt-4o-transcribe",
        )


if __name__ == "__main__":
    unittest.main()
