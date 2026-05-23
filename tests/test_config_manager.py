import os
import tempfile
import unittest
from pathlib import Path

try:
    from local_audio_transcriber import config as config_main
except ModuleNotFoundError:
    config_main = None


@unittest.skipIf(config_main is None, "Config module dependencies are not available in this Python environment.")
class ConfigManagerTests(unittest.TestCase):
    def setUp(self):
        self.original_config_file = config_main.CONFIG_FILE
        self.temp_dir_ctx = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_ctx.name)
        config_main.CONFIG_FILE = self.temp_dir / "config.json"

        self.original_env = dict(os.environ)

    def tearDown(self):
        config_main.CONFIG_FILE = self.original_config_file
        os.environ.clear()
        os.environ.update(self.original_env)
        self.temp_dir_ctx.cleanup()

    def test_theme_invalid_value_falls_back_to_system(self):
        manager = config_main.ConfigManager()
        manager.theme = "invalid"
        self.assertEqual(manager.theme, "System")

    def test_resolved_api_key_prefers_custom_environment_variable(self):
        os.environ["MY_OPENAI_KEY"] = "from-custom-env"
        os.environ["OPENAI_API_KEY"] = "from-default-env"

        manager = config_main.ConfigManager()
        manager.api_key_env_var = "MY_OPENAI_KEY"

        self.assertEqual(manager.resolved_api_key(), "from-custom-env")

    def test_resolved_api_key_ignores_stored_key(self):
        os.environ.pop("MY_OPENAI_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)

        config_main.CONFIG_FILE.write_text('{"api_key": "from-config"}', encoding="utf-8")
        manager = config_main.ConfigManager()
        manager.api_key_env_var = "MY_OPENAI_KEY"

        self.assertEqual(manager.resolved_api_key(), "")
        self.assertNotIn("api_key", manager.config)

    def test_resolved_api_key_falls_back_to_default_openai_env(self):
        os.environ["OPENAI_API_KEY"] = "from-default-env"
        os.environ.pop("MY_OPENAI_KEY", None)

        manager = config_main.ConfigManager()
        manager.api_key_env_var = "MY_OPENAI_KEY"

        self.assertEqual(manager.resolved_api_key(), "from-default-env")

    def test_live_recording_mode_defaults_to_live_transcript(self):
        manager = config_main.ConfigManager()
        self.assertEqual(manager.live_recording_mode, config_main.LIVE_TRANSCRIPT_MODE)

    def test_live_recording_mode_invalid_value_falls_back(self):
        manager = config_main.ConfigManager()
        manager.live_recording_mode = "invalid"
        self.assertEqual(manager.live_recording_mode, config_main.LIVE_TRANSCRIPT_MODE)

    def test_live_recording_mode_persists_valid_value(self):
        manager = config_main.ConfigManager()
        manager.live_recording_mode = config_main.RECORD_AND_TRANSCRIBE_MODE

        manager_reloaded = config_main.ConfigManager()
        self.assertEqual(
            manager_reloaded.live_recording_mode,
            config_main.RECORD_AND_TRANSCRIBE_MODE,
        )


if __name__ == "__main__":
    unittest.main()
