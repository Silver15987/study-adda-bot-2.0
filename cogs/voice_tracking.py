import discord
import asyncpg
import asyncio
import datetime
import os
import json
import logging
from discord.ext import commands, tasks
from dotenv import load_dotenv

# Load environment variables (DATABASE_URL)
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Load VC move settings from JSON
VC_CONFIG_FILE = "vc_settings.json"
default_config = {
    "timeout_duration": 300,  # Default to 5 minutes
    "response_timeout": 300   # Default to 5 minutes
}

if os.path.exists(VC_CONFIG_FILE):
    with open(VC_CONFIG_FILE, "r") as f:
        vc_config = json.load(f)
else:
    vc_config = default_config
    with open(VC_CONFIG_FILE, "w") as f:
        json.dump(vc_config, f, indent=4)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flag to enable or disable logging
ENABLE_LOGGING = True

# Global variables for timeout durations (in seconds)
TIMEOUT_DURATION = vc_config.get("timeout_duration", 300)  # Default to 5 minutes if not set in JSON
RESPONSE_TIMEOUT = vc_config.get("response_timeout", 300)  # Default to 5 minutes if not set in JSON

class TaskModal(discord.ui.Modal, title="Enter Your Task"):
    """Modal popup for users to enter their task"""

    task = discord.ui.TextInput(label="Task", placeholder="What are you working on?", required=True)
    timer = discord.ui.TextInput(label="Timer (minutes)", placeholder="Enter time in minutes (1-180)", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        """Handles task submission"""
        try:
            # Validate timer input
            timer_value = int(self.timer.value)
            if timer_value < 1 or timer_value > 180:
                raise ValueError("Timer value must be between 1 and 180 minutes.")

            if ENABLE_LOGGING:
                logger.info(f"🔹 Task Modal Submitted by: {interaction.user.id}")
                logger.info(f"🔹 Task Name Entered: {self.task.value}")
                logger.info(f"🔹 Timer Entered: {timer_value} minutes")

            end_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=timer_value)

            async with interaction.client.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO user_tasks (user_id, task, duration, end_time, status) VALUES ($1, $2, $3, $4, 'pending')",
                    interaction.user.id, self.task.value, timer_value, end_time
                )
                task_id = await conn.fetchval("SELECT id FROM user_tasks WHERE user_id = $1 AND task = $2 AND end_time = $3", interaction.user.id, self.task.value, end_time)
                interaction.client.task_queue.put_nowait((end_time, (interaction.user.id, task_id)))  # Add task to queue

            await interaction.response.send_message(
                f"✅ **Task:** {self.task.value}\n🕒 **Time:** {timer_value} minutes",
                ephemeral=True
            )
            # Mark the task as submitted for this session
            interaction.client.cogs['VoiceTracking'].task_submitted[interaction.user.id] = True

            if ENABLE_LOGGING:
                logger.info(f"🔹 New session created for user {interaction.user.id} with task {self.task.value} for {timer_value} minutes. Validity end time: {end_time}")
        except ValueError as ve:
            await interaction.response.send_message(f"❌ {ve}", ephemeral=True)
            await interaction.client.cogs['VoiceTracking'].kick_user_from_vc(interaction.user)
        except Exception as e:
            if ENABLE_LOGGING:
                logger.error(f"Error handling modal: {e}")
            await interaction.response.send_message("❌ Something went wrong. Try again.", ephemeral=True)
            await interaction.client.cogs['VoiceTracking'].kick_user_from_vc(interaction.user)

class TaskButtonView(discord.ui.View):
    """A button view that allows users to open the TaskModal"""

    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Enter Task", style=discord.ButtonStyle.primary)
    async def open_task_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Opens the TaskModal when button is clicked"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This button is not for you.", ephemeral=True)
            button.disabled = True
            await interaction.message.edit(view=self)
        else:
            await interaction.response.send_modal(TaskModal())

class TaskCompletionView(discord.ui.View):
    """Interactive buttons for task completion check"""

    def __init__(self, user, task_id):
        super().__init__(timeout=RESPONSE_TIMEOUT)  # Timeout for user response
        self.user = user
        self.task_id = task_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def complete_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Marks the task as completed"""
        async with interaction.client.pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_tasks SET status = 'completed' WHERE id = $1",
                self.task_id
            )
        await interaction.response.edit_message(content="✅ Task marked as completed!", view=None)
        await interaction.followup.send(
            "🎉 Congratulations on completing your task! Do you want to set a new task? Please set it within 5 minutes or you'll be removed from the voice chat.",
            view=TaskButtonView(self.user.id),
            ephemeral=True
        )

        if ENABLE_LOGGING:
            logger.info(f"🔹 Task {self.task_id} for user {self.user.id} marked as completed. Prompting for new task.")

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def task_not_completed(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Logs task as not completed and sends motivation"""
        async with interaction.client.pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_tasks SET status = 'left_early' WHERE id = $1",
                self.task_id
            )
        await interaction.response.edit_message(content="❌ Task not completed. Keep pushing forward! 💪", view=None)
        await interaction.followup.send(
            "How long of an extension do you want?",
            view=ExtensionSelectView(self.user.id),
            ephemeral=True
        )

        if ENABLE_LOGGING:
            logger.info(f"🔹 Task {self.task_id} for user {self.user.id} not completed. Prompting for extension.")

class ExtensionSelectView(discord.ui.View):
    """A view that allows users to select an extension duration"""

    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.select(
        placeholder="Select extension duration",
        options=[
            discord.SelectOption(label="1 minute", value="1"),  # Added for testing
            discord.SelectOption(label="15 minutes", value="15"),
            discord.SelectOption(label="30 minutes", value="30"),
            discord.SelectOption(label="45 minutes", value="45"),
            discord.SelectOption(label="60 minutes", value="60")
        ]
    )
    async def select_extension(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handles extension selection"""
        extension_value = int(select.values[0])
        end_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=extension_value)

        async with interaction.client.pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_tasks SET end_time = $1, duration = duration + $2 WHERE user_id = $3 AND status = 'pending' AND id = $4",
                end_time, extension_value, self.user_id, await conn.fetchval("SELECT id FROM user_tasks WHERE user_id = $1 AND status = 'pending' ORDER BY end_time DESC LIMIT 1", self.user_id)
            )
            task_id = await conn.fetchval(
                "SELECT id FROM user_tasks WHERE user_id = $1 AND status = 'pending' ORDER BY end_time DESC LIMIT 1",
                self.user_id
            )
            interaction.client.task_queue.put_nowait((end_time, (self.user_id, task_id)))  # Add task to queue

        if ENABLE_LOGGING:
            logger.info(f"🔹 Task for user {self.user_id} extended by {extension_value} minutes. New validity end time: {end_time}")

        await interaction.response.send_message(
            f"✅ Extension granted for {extension_value} minutes.",
            ephemeral=True
        )

class VoiceTracking(commands.Cog):
    """Tracks when users join voice channels and prompts for tasks"""

    def __init__(self, bot):
        self.bot = bot
        self.task_submitted = {}  # Dictionary to track task submission status
        if not hasattr(bot, "task_queue"):  # Ensure queue is initialized
            bot.task_queue = asyncio.PriorityQueue()
        if not hasattr(bot, "task_worker_started"):  # Prevent multiple workers
            bot.task_worker_started = True
            self.task_worker.start()  # Start processing the queue

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Detects when a user joins or leaves a voice channel and handles task prompts"""
        if before.channel is None and after.channel is not None:  # User joined a VC
            vc_channel = after.channel
            if ENABLE_LOGGING:
                logger.info(f"🔹 User {member} joined {vc_channel.name}")

            # Reset task_submitted flag for the new session
            self.task_submitted[member.id] = False

            await vc_channel.send(
                f"{member.mention}, click the button below to enter your task and time! If you don't respond, you will be removed from the voice chat.",
                view=TaskButtonView(member.id)
            )
            await asyncio.sleep(TIMEOUT_DURATION)  # Wait for the timeout duration
            if not self.task_submitted.get(member.id, False):
                await self.kick_user_from_vc(member)
        elif before.channel is not None and after.channel is None:  # User left VC early
            async with self.bot.pool.acquire() as conn:
                task = await conn.fetchrow(
                    "SELECT * FROM user_tasks WHERE user_id = $1 AND status = 'pending' ORDER BY end_time DESC LIMIT 1",
                    member.id
                )
                if task:
                    await conn.execute(
                        "UPDATE user_tasks SET status = 'left_early' WHERE id = $1",
                        task['id']
                    )
                    await self.handle_early_exit(member, task['id'])

    @tasks.loop(seconds=5)
    async def task_worker(self):
        """Continuously checks for tasks that need reminders or completion checks"""
        while True:
            now = datetime.datetime.utcnow()
            logger.info(f"🔹 task_worker check on time: {now}")

            # Load tasks within the next 2 hours
            async with self.bot.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM user_tasks WHERE end_time <= $1 AND status = 'pending' ORDER BY end_time ASC",
                    now + datetime.timedelta(hours=2)
                )
                for row in rows:
                    self.bot.task_queue.put_nowait((row['end_time'], (row['user_id'], row['id'])))

            if not self.bot.task_queue.empty():
                next_task = await self.bot.task_queue.get()
                task_time, (user_id, task_id) = next_task

                if ENABLE_LOGGING:
                    logger.info(f"Processing task for user {user_id} with task_id {task_id} and end_time {task_time}")

                # Wait until the task time
                await asyncio.sleep((task_time - now).total_seconds())

                user = self.bot.get_user(user_id)
                if user and user.voice and user.voice.channel:  # Check if user is still in a voice channel
                    await self.handle_post_task_check(user, task_id)
                else:
                    await self.mark_task_abandoned(user, task_id)
                    if ENABLE_LOGGING:
                        logger.info(f"🔹 User {user_id} is no longer in a voice channel. Task {task_id} marked as abandoned.")

    async def handle_post_task_check(self, user, task_id):
        """Handles checking if a user completed their task"""
        view = TaskCompletionView(user, task_id)
        await user.send("⏳ Your task time is up! Did you complete your task? If you don't respond within 5 minutes, you will be removed from the voice chat.", view=view)
        await asyncio.sleep(RESPONSE_TIMEOUT)  # Wait for the response timeout duration
        if not view.is_finished():
            await self.mark_task_abandoned(user, task_id)
            await self.kick_user_from_vc(user)

        if ENABLE_LOGGING:
            logger.info(f"🔹 Task {task_id} for user {user.id} validity over. Checking response.")

    async def handle_early_exit(self, user, task_id):
        """Handles cases where a user leaves VC before task completion"""
        view = TaskCompletionView(user, task_id)
        await user.send("❓ You left VC before your task ended. Did you complete your task? If you don't respond within 5 minutes, you will be removed from the voice chat.", view=view)
        await asyncio.sleep(RESPONSE_TIMEOUT)  # Wait for the response timeout duration
        if not view.is_finished():
            await self.mark_task_abandoned(user, task_id)
            await self.kick_user_from_vc(user)

        if ENABLE_LOGGING:
            logger.info(f"🔹 User {user.id} left VC early. Checking response for task {task_id}.")

    async def mark_task_abandoned(self, user, task_id):
        """Marks the task as abandoned"""
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_tasks SET status = 'abandoned' WHERE id = $1",
                task_id
            )
        if ENABLE_LOGGING:
            logger.info(f"🔹 Task {task_id} for user {user.id} marked as abandoned.")

    async def kick_user_from_vc(self, user):
        """Kicks the user from the voice chat"""
        if ENABLE_LOGGING:
            logger.info(f"Kicking user {user.id} from the voice chat due to inactivity.")
        for guild in self.bot.guilds:
            member = guild.get_member(user.id)
            if member and member.voice:
                await member.move_to(None)
                await user.send("❌ You have been removed from the voice chat due to inactivity.")
                if ENABLE_LOGGING:
                    logger.info(f"User {user.id} has been removed from the voice chat due to inactivity.")

async def setup(bot):
    bot.pool = await asyncpg.create_pool(DATABASE_URL)
    await bot.add_cog(VoiceTracking(bot))
