"""
Utility functions for the bot.
"""

# Standard library imports
import os

# Third party imports
from dotenv import dotenv_values


def load_environment() -> dict:
    """Load environment variables from .env files and the environment.
    Load in that order :
    - .env.shared
    - .env.secret
    - environment variables

    The latest loaded variables override the previous ones.

    Returns
    -------
        dict: The environment variables.
    """

    config = {
        **dotenv_values(".env.shared"),  # load shared development variables
        **dotenv_values(".env.secret"),  # load sensitive variables
        **os.environ,  # override loaded values with environment variables
    }

    return config

import re


ANIME_REGEX_REPLACE_RULES = [
    # Ļ can't lower correctly with sql lower function
    {"input": "ļ", "replace": "[ļĻ]"},
    {"input": "l", "replace": "[l˥ļĻΛ]"},
    # Ź can't lower correctly with sql lower function
    {"input": "ź", "replace": "[źŹ]"},
    {"input": "z", "replace": "[zźŹ]"},
    {"input": "ou", "replace": "(ou|ō|o)"},
    {"input": "oo", "replace": "(oo|ō|o)"},
    {"input": "oh", "replace": "(oh|ō|o)"},
    {"input": "wo", "replace": "(wo|o)"},
    {"input": "o", "replace": "([oōóòöôøӨΦο]|ou|oo|oh|wo)"},
    {"input": "uu", "replace": "(uu|u|ū)"},
    {"input": "u", "replace": "([uūûúùüǖμ]|uu)"},
    {"input": "aa", "replace": "(aa|a)"},
    {"input": "ae", "replace": "(ae|æ)"},
    {"input": "a", "replace": "([aäãά@âàáạåæā∀Λ]|aa)"},
    {"input": "c", "replace": "[cςč℃Ↄ]"},
    # É can't lower correctly with sql lower function
    {"input": "é", "replace": "[éÉ]"},
    {"input": "e", "replace": "[eəéÉêёëèæē]"},
    {"input": "'", "replace": "['’ˈ]"},
    {"input": "n", "replace": "[nñ]"},
    {"input": "0", "replace": "[0Ө]"},
    {"input": "2", "replace": "[2²]"},
    {"input": "3", "replace": "[3³]"},
    {"input": "5", "replace": "[5⁵]"},
    {"input": "*", "replace": "[*✻＊✳︎]"},
    {
        "input": " ",
        "replace": "( ?[²³⁵★☆♥♡\\/\\*✻✳︎＊'ˈ-∽~〜・·\\.,;:!?@_-⇔→≒=\\+†×±◎Ө♪♩♣␣∞] ?| )",
    },
    {"input": "i", "replace": "([iíίɪ]|ii)"},
    {"input": "x", "replace": "[x×]"},
    {"input": "b", "replace": "[bßβ]"},
    {"input": "r", "replace": "[rЯ]"},
    {"input": "s", "replace": "[sς]"},
]


def escape_and_replace(input_str: str) -> str:
    """Escape special characters and replace specific sequences.

    Parameters
    ----------
    input_str : str
        String to escape and replace.

    Returns
    -------
    str
        Escaped and replaced string.
    """

    escaped_str = re.escape(input_str)
    escaped_str = escaped_str.replace(r"\ ", " ")
    escaped_str = escaped_str.replace(r"\*", "*")
    return escaped_str


def apply_regex_rules(input_str: str) -> str:
    """Apply replacement rules using compiled regular expressions.

    Parameters
    ----------
    input_str : str
        String to apply replacement rules to.

    Returns
    -------
    str
        String with replacement rules applied.
    """

    output_str = input_str
    for rule in ANIME_REGEX_REPLACE_RULES:
        pattern = re.compile(re.escape(rule["input"]), re.IGNORECASE)
        output_str = pattern.sub(rule["replace"], output_str)
    return output_str


def generate_regex_pattern(input_str: str, partial_match: bool = True) -> str:
    """Generate a regex pattern for a string.
    Uses the rules defined in ANIME_REGEX_REPLACE_RULES.

    Parameters
    ----------
    input_str : str
        String to generate regex pattern for.

    partial_match : bool, optional
        Whether to match the whole string or not, by default True

    Returns
    -------
    str
        Regex pattern.
    """

    # Escape and replace special characters
    input_str = escape_and_replace(input_str.lower())

    # Apply replacement rules
    ouput_str = apply_regex_rules(input_str)

    # Allow partial match or not
    ouput_str = f".*{ouput_str}.*" if partial_match else f"^{ouput_str}$"

    return ouput_str


def process_user_input(
    input_str: str, partial_match: bool = True, swap_words: bool = True
) -> str:
    """Generate a regex pattern for a string.
    Uses the rules defined in ANIME_REGEX_REPLACE_RULES.

    Parameters
    ----------
    input_str : str
        String to generate regex pattern for.

    partial_match : bool, optional
        Whether to match the whole string or not, by default True

    swap_words : bool, optional
        Whether to allow to swap the order of the words or not, by default True
        Will allow to swap the order of the words if there are exactly two words.

    Returns
    -------
    str
        Regex pattern.
    """

    # Generate the regex pattern
    output_str = generate_regex_pattern(input_str, partial_match=partial_match)

    # if swap_words is False, or there isn't exactly two words, return the pattern
    if not swap_words or len(input_str.split(" ")) != 2:
        return output_str

    # else generate the pattern for the swapped user input, and return the pattern combined with the original pattern
    swapped_input_str = " ".join(input_str.split(" ")[::-1])
    swapped_output_str = generate_regex_pattern(
        swapped_input_str, partial_match=partial_match
    )
    output_str = f"({output_str})|({swapped_output_str})"

    return output_str


def extract_answer_from_user_input(user_input: str) -> str:
    """Extract the answer from a user input.
    The answer is the part of the user input, which start with either
    `female` or `male` and is inbetween the two `||`.

    Parameters
    ----------
    user_input : str
        User input.

    Returns
    -------
    str
        The extracted answer or None if no answer is found.

    Examples
    --------
    - `female ||Saori Hayami||` -> `Saori Hayami`
    - `male ||Yuuichi Nakamura||` -> `Yuuichi Nakamura`
    - `blah blah` -> None
    """

    # Define a pattern to search for the answer
    pattern = re.compile(r"(female|male)\s+\|\|(.+?)\|\|")

    # Use the pattern to search for matches in the message
    match = pattern.search(user_input)

    # Return None if no match is found
    if not match:
        return None

    # Otherwise, return the "answer" part
    return match.group(2)


