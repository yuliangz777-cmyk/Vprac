from lectureflow.config import Settings, load_dotenv, resolve_text_provider


class TestResolveTextProvider:
    def test_auto_prefers_anthropic(self):
        assert resolve_text_provider("auto", anthropic_key="a", openai_key="o") == "anthropic"

    def test_auto_falls_back_to_openai(self):
        assert resolve_text_provider("auto", anthropic_key="", openai_key="o") == "openai"

    def test_auto_with_no_keys(self):
        assert resolve_text_provider("auto", anthropic_key="", openai_key="") == "none"

    def test_explicit_choice_is_honoured(self):
        assert resolve_text_provider("openai", anthropic_key="a", openai_key="o") == "openai"

    def test_explicit_choice_without_its_key_is_unusable(self):
        assert resolve_text_provider("anthropic", anthropic_key="", openai_key="o") == "none"


class TestSettings:
    def test_no_fictional_model_defaults(self):
        settings = Settings()
        assert settings.anthropic_model == "claude-opus-5"
        assert settings.openai_text_model == "gpt-4o-mini"
        assert settings.transcribe_model == "gpt-4o-mini-transcribe"

    def test_transcribe_key_falls_back_to_the_openai_key(self):
        assert Settings(openai_api_key="o").transcribe_key == "o"
        assert Settings(openai_api_key="o", transcribe_api_key="t").transcribe_key == "t"

    def test_a_local_endpoint_needs_no_key(self):
        local = Settings(transcribe_base_url="http://127.0.0.1:8080/v1")
        assert local.transcribe_ready is True
        assert Settings().transcribe_ready is False

    def test_text_model_follows_the_resolved_provider(self):
        assert Settings(resolved_text_provider="anthropic").text_model == "claude-opus-5"
        assert Settings(resolved_text_provider="openai").text_model == "gpt-4o-mini"
        assert Settings().text_model == ""


class TestDotenv:
    def test_reads_pairs_without_clobbering_the_environment(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text(
            '# comment\nFROM_FILE=value\nQUOTED="quoted value"\nALREADY_SET=file\n\n',
            encoding="utf-8",
        )
        monkeypatch.delenv("FROM_FILE", raising=False)
        monkeypatch.delenv("QUOTED", raising=False)
        monkeypatch.setenv("ALREADY_SET", "environment")

        load_dotenv(env_file)

        import os

        assert os.environ["FROM_FILE"] == "value"
        assert os.environ["QUOTED"] == "quoted value"
        assert os.environ["ALREADY_SET"] == "environment"

    def test_missing_file_is_not_an_error(self, tmp_path):
        load_dotenv(tmp_path / "nope.env")
