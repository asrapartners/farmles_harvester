from farmles_harvester.stages.normalize_source_leads import parse_seed_lines


class TestParseSeedLines:
    def test_skips_blank_lines(self):
        leads = parse_seed_lines("\n\nhttps://example.com\n\n")
        assert len(leads) == 1

    def test_skips_comment_lines(self):
        leads = parse_seed_lines("# NC markets\nhttps://example.com")
        assert len(leads) == 1
        assert leads[0].input_url == "https://example.com"

    def test_assigns_slug_from_url(self):
        leads = parse_seed_lines("https://example.com\nhttps://other.com")
        assert leads[0].source_slug == "example-com"
        assert leads[1].source_slug == "other-com"

    def test_preserves_input_url(self):
        leads = parse_seed_lines("apexfarmersmarket.com")
        assert leads[0].input_url == "apexfarmersmarket.com"

    def test_stores_normalized_url(self):
        leads = parse_seed_lines("apexfarmersmarket.com")
        assert leads[0].normalized_url == "https://apexfarmersmarket.com/"

    def test_preserves_input_line_number(self):
        text = "# comment\n\napexfarmersmarket.com\nhttps://other.com"
        leads = parse_seed_lines(text)
        assert leads[0].input_line == 3
        assert leads[1].input_line == 4

    def test_deduplicates_by_normalized_url(self):
        text = "apexfarmersmarket.com\nhttps://apexfarmersmarket.com/"
        leads = parse_seed_lines(text)
        assert len(leads) == 1

    def test_does_not_create_duplicate_records(self):
        text = "apexfarmersmarket.com\nhttps://apexfarmersmarket.com/\nhttps://other.com"
        leads = parse_seed_lines(text)
        assert len(leads) == 2
        normalized = [l.normalized_url for l in leads]
        assert len(normalized) == len(set(normalized))
