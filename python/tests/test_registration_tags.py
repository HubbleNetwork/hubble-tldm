from hubbledemo.cli import registration_tags_for_board


def test_satellite_boards_get_next_pass_tag():
    assert registration_tags_for_board("nrf21540dk_sat") == {
        "satellite": "next-pass"
    }
    assert registration_tags_for_board("xg24_rb4187c_sat") == {
        "satellite": "next-pass"
    }


def test_terrestrial_boards_get_no_tags():
    assert registration_tags_for_board("nrf21540dk") is None
    assert registration_tags_for_board("nrf52840dk") is None
    assert registration_tags_for_board("xg24_ek2703a") is None
