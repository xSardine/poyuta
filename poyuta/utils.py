"""
Utility functions for the bot.
"""

# Standard library imports
import os
import re
from datetime import datetime, date, time, timedelta

# Discord.py
from discord import app_commands, Embed

# Third party imports
from dotenv import dotenv_values

# Database models
from poyuta.database import Quiz, QuizType, Answer, User

# Typing helpers
from sqlalchemy.orm.session import Session

# Define a list of replacement rules
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


def is_admin(session: Session, user: User):
    """Check if a user is an admin.

    Parameters
    ----------
    session : Session
        Database session.

    user : User
        User to check.

    Returns
    -------
    bool
        Whether the user is an admin or not.
    """

    admins = session.query(User).filter(User.is_admin == True).all()

    if user.id in [admin.id for admin in admins]:
        return True
    else:
        return False


def generate_stats_embed_content(session: Session, embed: Embed, answers: list[Answer]):
    """Generate the stats embed content.

    Parameters
    ----------
    session : Session
        Database session.

    embed : Embed
        Embed to fill.

    answers : list[Answer]
        List of answers to process.

    Returns
    -------
    Embed
        Filled embed.
    """

    nb_unique_quizzes = len(set([answer.quiz_id for answer in answers]))

    # Guess Rates
    nb_correct_answers = len([answer for answer in answers if answer.is_correct])
    guess_rate = (
        round(nb_correct_answers / nb_unique_quizzes * 100, 2)
        if nb_unique_quizzes
        else "N/A"
    )
    embed.add_field(
        name="> :dart: Guess Rate",
        value=f"> {guess_rate}% ({nb_correct_answers}/{nb_unique_quizzes})",
        inline=True,
    )

    # Average Guess Time
    # TODO retrieve from database once implemented
    # Hard coded for now for testing purposes
    embed.add_field(name="> :clock1: Average Guess Time", value="> N/A", inline=True)

    embed.add_field(name="", value="", inline=False)

    # Total attempts
    embed.add_field(
        name="> :1234: Total Attempts",
        value=f"> {len(answers)} attempt(s)",
        inline=True,
    )

    # Average number of attempts per quiz
    unique_quizzes = set([answer.quiz_id for answer in answers])
    average_attempts = (
        round(len(answers) / len(unique_quizzes), 2) if unique_quizzes else "N/A"
    )
    embed.add_field(
        name="> :repeat: Average Attempts",
        value=f"> {average_attempts} attempt(s)",
        inline=True,
    )

    embed.add_field(name="", value="", inline=False)

    # Fastest Guesses
    # TODO retrieve from database once implemented
    # Hard coded for now for testing purposes
    fastest_guesses = [
        {
            "date": "2023-11-05",
            "guess_time": "N/A",
            "attempts": 1,
            "answer": "Saori Hayami",
        },
        {
            "date": "2023-10-25",
            "guess_time": "N/A",
            "attempts": 3,
            "answer": "Rie Takahashi",
        },
        {
            "date": "2023-09-20",
            "guess_time": "N/A",
            "attempts": 5,
            "answer": "Hiro Shimono",
        },
    ]

    medals = [":first_place:", ":second_place:", ":third_place:"]

    fastest_guesses = "\n\n".join(
        [
            f"{medals[i]} | **{guess['guess_time']}s** : {guess['answer']} in {guess['attempts']} attempts on {guess['date']}"
            for i, guess in enumerate(fastest_guesses)
        ]
    )

    embed.add_field(
        name="__Fastest guesses__",
        value=fastest_guesses,
        inline=True,
    )

    return embed


def get_current_quiz_date(daily_quiz_reset_time: time) -> date:
    """Get the current quiz date.
    The current quiz date is yesterday if it's before the daily quiz reset time,
    else it's today.

    Parameters
    ----------
    daily_quiz_reset_time : time
        Time at which the daily quiz resets. HH:MM:SS format.

    Returns
    -------
    date
        Current quiz date.
    """

    # get time now
    now = datetime.now()

    # today's quiz is yesterday date if it's before the daily quiz reset time
    # else it's today's date
    return (
        now.date()
        if now.time() >= daily_quiz_reset_time
        else now.date() - timedelta(days=1)
    )


def get_user_from_id(
    session: Session,
    user_id: int,
    add_if_not_exist: bool = True,
    user_name: str = None,
):
    """Get the user from the database from its discord ID.

    Parameters
    ----------
    session : Session
        Database session.

    user_id : int
        User discord ID.

    add_if_not_exist : bool, optional
        Whether to add the user to the database if it doesn't exist, by default True.

    user_name : str
        User name if the user is added to the database.

    Returns
    -------
    User
        User from the database.
    """

    user = session.query(User).filter(User.id == user_id).first()

    if not user and add_if_not_exist:
        if not user_name:
            raise ValueError("user_name must be provided if add_if_not_exist is True")

        user = User(id=user_id, name=user_name, is_admin=False)
        session.add(user)
        session.commit()

    return user


def get_quiz_type_choices(session: Session) -> list[tuple[int, str]]:
    """Get the quiz type choices.

    Parameters
    ----------
    session : Session
        Database session.

    Returns
    -------
    list[tuple[int, str]]
        List of quiz type choices.
    """

    quiz_types = session.query(QuizType).distinct().all()

    return [
        app_commands.Choice(value=quiz_type.id, name=quiz_type.type)
        for quiz_type in quiz_types
    ]
