# Standard libraries
import re
from datetime import datetime, date, timedelta
from typing import Optional

# Discord
import discord
from discord import app_commands, Embed, Button, ButtonStyle
from discord.ext import commands
import random
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Database
from poyuta.database import (
    UserStartQuizTimestamp,
    Quiz,
    QuizType,
    Answer,
    SessionFactory,
    initialize_database,
)


# Utils
from poyuta.utils import (
    load_environment,
    process_user_input,
    get_current_quiz_date,
    get_user_from_id,
    get_quiz_type_choices,
    is_admin,
    generate_stats_embed_content,
)

config = load_environment()
DAILY_QUIZ_RESET_TIME = datetime.strptime(
    config["DAILY_QUIZ_RESET_TIME"], "%H:%M:%S"
).time()

intents = discord.Intents.all()
intents.reactions = True
intents.messages = True

initialize_database(config["DEFAULT_ADMIN_ID"], config["DEFAULT_ADMIN_NAME"])


# Update bot class to include the session property
class PoyutaBot(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)

    # add database session to bot
    # can now be access through bot.session
    @property
    def session(self):
        return SessionFactory()


# Instantiate bot
bot = PoyutaBot(command_prefix=config["COMMAND_PREFIX"], intents=intents)


@bot.event
async def on_ready():
    print(f"logged in as {bot.user.name}")

    try:
        synced = await bot.tree.sync()
        print(f"synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        post_yesterdays_quiz_results,
        "cron",
        hour=DAILY_QUIZ_RESET_TIME.hour,
        minute=DAILY_QUIZ_RESET_TIME.minute,
        second=DAILY_QUIZ_RESET_TIME.second,
    )
    scheduler.start()


@bot.command()  # for quick debugging
async def postquizresults(ctx):
    await post_yesterdays_quiz_results()


@bot.tree.command(name="newquiz")
@app_commands.choices(quiz_type=get_quiz_type_choices(session=bot.session))
@app_commands.describe(
    quiz_type="type of the quiz to update",
    new_clip="input new clip for female",
    new_answer="input new seiyuu for female clip",
)
async def new_quiz(
    interaction: discord.Interaction,
    quiz_type: app_commands.Choice[int],
    new_clip: str,
    new_answer: str,
):
    """*Admin only* - create a new quiz."""

    with bot.session as session:
        if not is_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command."
            )
            return

        latest_quiz = (
            session.query(Quiz)
            .filter(Quiz.id_type == quiz_type.value)
            .order_by(Quiz.date.desc())
            .first()
        )

        # get current date
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # if the latest quiz date is in the future
        # that means there's already a quiz for today, so add the new date to the planned quizzes
        # i.e latest quiz date + 1 day
        if latest_quiz and latest_quiz.date >= current_quiz_date:
            new_date = latest_quiz.date + timedelta(days=1)
        # else there aren't any quiz today, so the new date is today
        else:
            new_date = current_quiz_date

        # add the new quizzes to database
        new_quiz = Quiz(
            creator_id=interaction.user.id,
            clip=new_clip,
            answer=new_answer,
            id_type=quiz_type.value,
            date=new_date,
        )
        session.add(new_quiz)
        session.commit()

    await interaction.response.send_message(
        f"New {quiz_type.name} quiz created on {new_date}."
    )


@bot.tree.command(name="updatequiz")
@app_commands.choices(quiz_type=get_quiz_type_choices(session=bot.session))
@app_commands.describe(
    quiz_date="date of the quiz to update in YYYY-MM-DD format",
    quiz_type="type of the quiz to update",
    new_clip="input new clip for female",
    new_answer="input new seiyuu for female clip",
)
async def update_quiz(
    interaction: discord.Interaction,
    quiz_date: str,
    quiz_type: app_commands.Choice[int],
    new_clip: str,
    new_answer: str,
):
    """*Admin only* - Update a planned quiz."""

    with bot.session as session:
        if not is_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command."
            )
            return

        try:
            quiz_date = datetime.strptime(quiz_date, "%Y-%m-%d").date()
        except ValueError:
            await interaction.response.send_message(
                "Invalid date format. Please use YYYY-MM-DD."
            )
            return

        # check the date is in the future
        if quiz_date <= get_current_quiz_date(DAILY_QUIZ_RESET_TIME):
            await interaction.response.send_message(
                "You can only update a quiz that hasn't happened yet. Please use a date in the future."
            )
            return

        # check if that quiz exists for this quiz_type and quiz_date
        quiz = (
            session.query(Quiz)
            .filter(Quiz.id_type == quiz_type.value, Quiz.date == quiz_date)
            .first()
        )

        if not quiz:
            await interaction.response.send_message(
                f"No {quiz_type.name} quiz on {quiz_date}. Can't update it."
            )
            return

        # Update attributes
        quiz.clip = new_clip
        quiz.answer = new_answer

        # Commit the changes to the database
        session.commit()

        await interaction.response.send_message(
            f"{quiz_type.name} quiz updated for {quiz_date}."
        )


@bot.tree.command(name="plannedquizzes")
async def planned_quizzes(interaction: discord.Interaction):
    """*Admin only* - Check the planned quizzes."""

    with bot.session as session:
        if not is_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command."
            )
            return

        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # get all the quizzes that are planned after the current quiz
        unique_date = (
            session.query(Quiz.date)
            .filter(Quiz.date >= current_quiz_date)
            .distinct()
            .all()
        )

        if not unique_date:
            await interaction.response.send_message(
                f"No planned quizzes after {current_quiz_date}."
            )
            return

        embed = discord.Embed(title="Planned Quizzes")

        # get all the quiz types
        quiz_types = session.query(QuizType).all()

        for i, quiz_date in enumerate(unique_date):
            quiz_date = quiz_date[0]

            embed.add_field(
                name=f":calendar_spiral: __**{quiz_date if i != 0 else 'Today'}**__",
                value="",
                inline=False,
            )

            for i, quiz_type in enumerate(quiz_types):
                # get quiz for this type and date
                quiz = (
                    session.query(Quiz)
                    .filter(Quiz.id_type == quiz_type.id, Quiz.date == quiz_date)
                    .first()
                )
                value = (
                    f"[{quiz.answer}]({quiz.clip})"
                    if quiz
                    else "Nothing planned :disappointed_relieved:"
                )
                embed.add_field(
                    name=f"> {quiz_type.emoji} {quiz_type.type}",
                    value=f"> {value}",
                    inline=True,
                )

                # Linebreak every two types unless last type
                if i % 2 == 0 and i != 0 and i != len(quiz_types) - 1:
                    embed.add_field(name="", value="", inline=False)

            # Linebreak unless last date
            if quiz_date != unique_date[-1][0]:
                embed.add_field(name="\u200b", value="", inline=False)

        await interaction.response.send_message(embed=embed)


@bot.tree.command(name="answerquiz")
@app_commands.describe(
    quiz_type="type of the quiz to answer", answer="your answer for this quiz"
)
@app_commands.choices(quiz_type=get_quiz_type_choices(session=bot.session))
async def anwswer_quiz(
    interaction: discord.Interaction, quiz_type: app_commands.Choice[int], answer: str
):
    """guess the seiyuu for the current quiz_type quiz."""

    answer_time = datetime.now()

    with bot.session as session:
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # get quiz for this date and type
        quiz = (
            session.query(Quiz)
            .filter(Quiz.id_type == quiz_type.value, Quiz.date == current_quiz_date)
            .first()
        )
        if not quiz:
            await interaction.response.send_message(
                f"No {quiz_type.name} quiz today :disappointed_relieved:"
            )

        user = get_user_from_id(
            session=session,
            user_id=interaction.user.id,
            add_if_not_exist=True,
            user_name=interaction.user.name,
        )

        # if the user has already answered the quiz correctly
        # don't let them answer again
        for answer in user.answers:
            if answer.quiz_id == quiz.id and answer.is_correct:
                await interaction.response.send_message(
                    f"You have already answered correctly for today's {quiz_type.name} quiz."
                )
                return

        # get the time at which the user clicked the button
        start_quiz_timestamp = (
            session.query(UserStartQuizTimestamp)
            .filter(
                UserStartQuizTimestamp.user_id == user.id,
                UserStartQuizTimestamp.quiz_id == quiz.id,
            )
            .first()
        )

        # if the user hasn't clicked the button yet
        # don't let them answer
        if not start_quiz_timestamp:
            await interaction.response.send_message(
                f"You haven't started the {quiz_type.name} quiz yet. How do you know the answer? :HMM:"
            )
            return

        # compute answer time in seconds
        answer_time = answer_time - start_quiz_timestamp.timestamp
        answer_time = answer_time.total_seconds()

    # create the answer object
    user_answer = Answer(
        user_id=user.id,
        quiz_id=quiz.id,
        answer=answer,
        answer_time=answer_time,
    )

    # Generate a pattern to match with the correct answer
    user_answer_pattern = process_user_input(
        user_answer.answer, partial_match=False, swap_words=True
    )

    # If the pattern matches : the answer is correct
    if re.search(user_answer_pattern, quiz.answer):
        # Send feedback to the user
        await interaction.response.send_message("✅")

        # Store the user's answer in the Answer table
        with bot.session as session:
            user_answer.is_correct = True
            session.add(user_answer)
            session.commit()

    # Otherwise, the pattern doesn't match : the answer is incorrect
    else:
        # Send feedback to the user
        await interaction.response.send_message("❌")

        # Store the user's answer in the Answer table
        with bot.session as session:
            user_answer.is_correct = False
            session.add(user_answer)
            session.commit()


@bot.tree.command(name="mystats")
async def my_stats(interaction: discord.Interaction):
    """get your stats."""

    with bot.session as session:
        # get the user
        user = get_user_from_id(
            session=session,
            user_id=interaction.user.id,
            add_if_not_exist=False,
        )

        if not user:
            await interaction.response.send_message("You have not played yet.")
            return

        # create the embed object
        embed = discord.Embed(title="")
        # Get the user's avatar URL
        avatar_url = interaction.user.avatar.url
        embed.set_author(name=interaction.user.name, icon_url=avatar_url)

        quiz_types = session.query(QuizType).all()
        for quiz_type in quiz_types:
            # get the answers for this user and this quiz type
            embed.add_field(
                name=f"{quiz_type.emoji} {quiz_type.type}", value="", inline=False
            )

            # generate the embed content for this quiz_type
            embed = generate_stats_embed_content(
                session=session,
                embed=embed,
                answers=[
                    answer
                    for answer in user.answers
                    if answer.quiz.id_type == quiz_type.id
                ],
            )

            # Linebreak unless last quiz type
            if quiz_type != quiz_types[-1]:
                embed.add_field(name="\u200b", value="", inline=False)

    await interaction.response.send_message(embed=embed)


@bot.event
async def post_yesterdays_quiz_results():
    channel_id = int(config["CHANNEL_ID"])  # Replace with the actual channel ID
    channel = bot.get_channel(channel_id)

    if not channel:
        print("Invalid channel ID.")
        # await channel.send("Invalid channel ID.")
        return

    # Calculate the date for yesterday
    current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)
    yesterday = current_quiz_date - timedelta(days=1)

    embed = discord.Embed(
        title=f"Yesterday's Quiz Results ({yesterday})",
        color=0xBBE6F3,
    )

    # TODO : add the author of the quiz in database and retrieve it from there
    embed.set_author(
        name=config["NEWQUIZ_EMBED_AUTHOR"], icon_url=config["AUTHOR_ICON_URL"]
    )

    # Query the database for the quiz that matches the calculated date
    with bot.session as session:
        quiz_types = session.query(QuizType).all()
        for i, quiz_type in enumerate(quiz_types):
            # get yesterday's male quiz
            yesterday_quiz = (
                session.query(Quiz)
                .filter(Quiz.id_type == quiz_type.id, Quiz.date == yesterday)
                .first()
            )

            embed.add_field(
                name=f"> {quiz_type.emoji} {quiz_type.type}",
                value=f"> ||{yesterday_quiz.answer}||"
                if yesterday_quiz
                else "> No quiz took place :disappointed_relieved:",
                inline=True,
            )
            embed.add_field(
                name="> Clip",
                value=f"> {yesterday_quiz.clip}" if yesterday_quiz else "> N/A",
                inline=True,
            )

            # Linebreak
            embed.add_field(name="", value="", inline=False)

            # Top Guesseres TODO
            embed.add_field(
                name="> Top Guessers",
                value=f"> TBA\n> TBA\n> TBA",
                inline=True,
            )

            # TODO
            embed.add_field(name="> Time(?)", value="> TBA\n> TBA\n> TBA", inline=True)
            embed.add_field(name="> Attempts", value="> TBA\n> TBA\n> TBA", inline=True)
            embed.add_field(name="Most Guessed", value="TBA", inline=False)

            # Linebreak unless last quiz type
            if quiz_type != quiz_types[-1]:
                embed.add_field(name="\u200b", value="", inline=False)

        # Create a single View
        view = NewQuizView()

        # Send the message with the view
        await channel.send(embed=embed, view=view)


class NewQuizButton(discord.ui.Button):
    """
    Class for the NewQuizButton
    """

    def __init__(
        self,
        quiz_type: QuizType,
        new_quiz_date: date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        ),
    ):
        super().__init__(
            label=f"Play today's {quiz_type.type} Quiz",
            style=discord.ButtonStyle.green,
        )

        self.new_quiz_date = new_quiz_date
        self.quiz_type = quiz_type

    async def callback(self, interaction: discord.Interaction):
        with bot.session as session:
            # get quiz
            current_quiz = (
                session.query(Quiz)
                .filter(
                    Quiz.id_type == self.quiz_type.id,
                    Quiz.date == self.new_quiz_date,
                )
                .first()
            )

            if not current_quiz:
                await interaction.response.send_message(
                    f"No {self.quiz_type.type} quiz today :disappointed_relieved:",
                    ephemeral=True,
                )
                return

            user = get_user_from_id(
                session=session,
                user_id=interaction.user.id,
                add_if_not_exist=True,
                user_name=interaction.user.name,
            )

            # if they already clicked it before
            # don't let them click it again
            if user.id not in [
                start_time.user_id for start_time in current_quiz.start_quiz_timestamps
            ]:
                # Add the timestamp at which they clicked the button in db
                new_start_quiz_timestamp = UserStartQuizTimestamp(
                    user_id=user.id,
                    quiz_id=current_quiz.id,
                    timestamp=datetime.now(),
                )
                session.add(new_start_quiz_timestamp)
                session.commit()

            await interaction.response.send_message(
                f"**{self.quiz_type.type} clip:** {current_quiz.clip}", ephemeral=True
            )


class NewQuizView(discord.ui.View):
    def __init__(self):
        super().__init__()

        with bot.session as session:
            for quiz_type in session.query(QuizType).all():
                button = NewQuizButton(quiz_type=quiz_type)
                self.add_item(button)
