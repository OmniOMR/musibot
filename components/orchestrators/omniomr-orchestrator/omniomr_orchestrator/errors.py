class UnreadableLayout(ValueError):
    """The `layout.json` is not one this *Pipeline* can slice a page along.

    Raised with a message written for the *User* who will see it, since a
    *Pipeline Execution's* error is what reaches them.
    """


class UnreadableTranscription(ValueError):
    """A staff transcription is not MusicXML this can take measures out of."""


class MissingMeasure(ValueError):
    """
    Number of measures inside this staff is lower than expected.
    Expected number of measures is derived from the global layout
    context - the maximum of measures in one staff in a system.
    """
