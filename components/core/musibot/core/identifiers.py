"""Random identifiers, of the one shape Musibot uses everywhere.

Page IDs, provider instance IDs and model execution IDs are all the same
thing — a short random string — so they are generated in one place.
"""

import secrets
import string

ID_LENGTH = 12

# A NanoID alphabet, restricted to alphanumerics. The usual NanoID alphabet
# also has `-` and `_`; they are dropped because an ID may become a directory
# name, and a directory whose name begins with `-` is a nuisance to every
# command line tool that would ever look at it. 62^12 is ample either way.
ID_ALPHABET = string.ascii_letters + string.digits


def random_id(length: int = ID_LENGTH) -> str:
    """Make up a new identifier.

    IDs are random rather than sequential so that they cannot be guessed or
    enumerated — which for page IDs is defense in depth behind the ownership
    check in the `api` service.
    """
    return "".join(secrets.choice(ID_ALPHABET) for _ in range(length))


def is_well_formed_id(value: str, length: int = ID_LENGTH) -> bool:
    """Whether the value has the shape of an identifier Musibot would issue."""
    return len(value) == length and all(character in ID_ALPHABET for character in value)
