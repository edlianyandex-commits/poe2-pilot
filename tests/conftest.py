import pytest


@pytest.fixture(autouse=True)
def russian_ui():
    """Tests read the Russian texts; the CI runner's Windows is English, so pin the language."""
    from pilot import i18n
    i18n.set_lang("ru")
    yield
    i18n.set_lang("ru")
