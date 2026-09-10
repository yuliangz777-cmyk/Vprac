from lectureflow import textproc


class TestJoinTranscript:
    def test_appends_plain_text(self):
        assert textproc.join_transcript("第一句。", "第二句。") == "第一句。第二句。"

    def test_removes_overlap_from_a_forced_cut(self):
        previous = "今天我們談的是供給曲線"
        assert textproc.join_transcript(previous, "供給曲線會往右移動") == "今天我們談的是供給曲線會往右移動"

    def test_overlap_detection_ignores_spacing(self):
        assert textproc.join_transcript("the supply curve", "supply  curve shifts right") == (
            "the supply curve shifts right"
        )

    def test_inserts_a_space_between_latin_words_only(self):
        assert textproc.join_transcript("hello", "there") == "hello there"
        assert textproc.join_transcript("你好", "世界") == "你好世界"

    def test_short_coincidental_overlap_is_kept(self):
        # Two characters is below the overlap threshold; dropping it would eat text.
        assert textproc.join_transcript("結論是的", "的確如此") == "結論是的的確如此"

    def test_empty_inputs(self):
        assert textproc.join_transcript("", "只有這句") == "只有這句"
        assert textproc.join_transcript("已有內容", "   ") == "已有內容"


class TestCleanChunk:
    def test_keeps_real_speech(self):
        assert textproc.clean_transcript_chunk(" 這是真的內容。 ") == "這是真的內容。"

    def test_drops_known_silence_hallucinations(self):
        for artifact in ["謝謝觀看", "字幕由Amara.org社群提供", "Thanks for watching!", "。。。"]:
            assert textproc.clean_transcript_chunk(artifact) == "", artifact

    def test_drops_blank_and_whitespace(self):
        assert textproc.clean_transcript_chunk("") == ""
        assert textproc.clean_transcript_chunk("   \n ") == ""

    def test_collapses_a_looping_model(self):
        assert textproc.clean_transcript_chunk("好的的的的的的的的") == "好的的"
        assert textproc.clean_transcript_chunk("我們繼續我們繼續我們繼續我們繼續") == "我們繼續我們繼續"


class TestParseNotes:
    def test_parses_a_clean_object(self):
        notes = textproc.parse_notes(
            '{"summary":["一"],"concepts":[{"term":"需求","explanation":"想買的量"}],'
            '"exam_points":[],"open_questions":["為什麼"],"latest":"在講需求"}'
        )
        assert notes["summary"] == ["一"]
        assert notes["concepts"] == [{"term": "需求", "explanation": "想買的量"}]
        assert notes["open_questions"] == ["為什麼"]
        assert notes["latest"] == "在講需求"

    def test_strips_code_fences_and_prose(self):
        notes = textproc.parse_notes('好的：\n```json\n{"summary":["甲"]}\n```')
        assert notes["summary"] == ["甲"]
        assert notes["concepts"] == []

    def test_falls_back_to_free_text(self):
        notes = textproc.parse_notes("模型只回了一段話")
        assert notes["summary"] == ["模型只回了一段話"]

    def test_tolerates_wrong_shapes(self):
        notes = textproc.parse_notes('{"summary":"單一字串","concepts":["名詞"],"latest":null}')
        assert notes["summary"] == ["單一字串"]
        assert notes["concepts"] == [{"term": "名詞", "explanation": ""}]
        assert notes["latest"] == ""
