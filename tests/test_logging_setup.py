import logging
import tempfile
import unittest
from pathlib import Path

from local_audio_transcriber.logging_setup import LOG_FILE_NAME, setup_logging


class LoggingSetupTests(unittest.TestCase):
    def test_setup_logging_creates_logs_folder_and_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_home = Path(temp_dir) / ".local-transcriber"
            log_dir = setup_logging(app_home_dir=app_home, force=True)
            try:
                logging.getLogger("local_audio_transcriber.tests").info("test log line")

                log_file = log_dir / LOG_FILE_NAME
                self.assertTrue(log_dir.exists())
                self.assertTrue(log_file.exists())
                self.assertIn("test log line", log_file.read_text(encoding="utf-8"))
            finally:
                # Release file handles so TemporaryDirectory cleanup works on Windows.
                root_logger = logging.getLogger()
                for handler in list(root_logger.handlers):
                    root_logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
