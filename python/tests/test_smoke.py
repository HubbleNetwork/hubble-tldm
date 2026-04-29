def test_package_imports():
    import hubbledemo

    assert hubbledemo.flash_elf
    assert hubbledemo.patch_elf
    assert hubbledemo.fetch_elf
    assert hubbledemo.fetch_metadata


def test_cli_imports():
    from hubbledemo import cli

    assert cli.main
