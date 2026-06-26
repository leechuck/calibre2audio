"""Calibre plugin: Calibre2Audio.

A thin GUI front-end. The heavy lifting (Kokoro neural TTS, ffmpeg) lives in the
standalone `calibre2audio` command-line tool, which runs in its own environment
with PyTorch. Calibre's embedded Python cannot host PyTorch, so this plugin just
collects parameters and shells out to that CLI as a background job.
"""

from calibre.customize import InterfaceActionBase


class Calibre2AudioPlugin(InterfaceActionBase):
    name = "Calibre2Audio"
    description = (
        "Generate a run-length MP3 from the selected book using the "
        "calibre2audio CLI (Kokoro neural TTS), starting from a phrase you "
        "just read on your Kindle, or resuming from the last export."
    )
    supported_platforms = ["windows", "osx", "linux"]
    author = "Robert Hoehndorf"
    version = (1, 0, 0)
    minimum_calibre_version = (6, 0, 0)

    actual_plugin = "calibre_plugins.calibre2audio.ui:InterfacePlugin"

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.calibre2audio.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
        ac = self.actual_plugin_
        if ac is not None:
            ac.apply_settings()
