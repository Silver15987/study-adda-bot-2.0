#Event message: Ui Modal, on user select give the user a role from a specific team for the event. 

# let user create new events

# Let user create new teams, specify roles for the teams and assign them to users (automatically)

# Create event announcements




#install all the packages
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import datetime
from datetime import datetime

load_dotenv()

TEAM_EMOJI = "✅" #emoji triggering the team assignment
ALL_TEAMS = ["Team Alpha", "Team Beta", "Team Gamma", "Team Lambda"]

#In-memory rotation setup
a1 = ALL_TEAMS.copy()
a2 = []

class Client(commands.Bot):
    async def on_ready(self):
        print(f'Logged on as {self.user}!')

        try:
            guild = discord.Object(id=os.getenv("GUILD"))
            synced = await self.tree.sync(guild=guild)
            print(f'Synced {len(synced)} commands to guild {guild.id}')

        except Exception as e:
            print(f'Error syncing commands: {e}')

    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.a1 = []
        self.a2 = []
        self.target_message_id = None
        self.team_map = {}          #team name -> [user_ids]

    
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.user.id or payload.message_id != self.target_message_id:
            return
        
        guild = self.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)

        if not member or not self.a1 and not self.a2:
            return
        
        if not self.a1:
            self.a1, self.a2 = self.a2, []

        import random
        team = random.choice(self.a1)
        self.a1.remove(team)
        self.a2.append(team)

        role = discord.utils.get(guild.roles, name = team)
        if not role:
            role = await guild.create_role(name = team)
            print(f'Created missing Role: {team}')

        await member.add_roles(role)

        self.team_map.setdefault(team, [])
        self.team_map[team].append(payload.user_id)
        print(f'Assigned {role.name} to {member.display_name}')

        #update embed (optional live update)
        channel = guild.get_channel(int(os.getenv("CHANNEL_ID")))
        try:
            msg = await channel.fetch_message(self.target_message_id)
            await msg.edit(embed=create_team_embed(member, list(self.team_map.keys()), self.team_map))
        except Exception as e:
            print(f"Failed to update embed: {e}")



intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True
# intents.guilds = True
client = Client(command_prefix=".", intents=intents)


GUILD_ID = discord.Object(id=os.getenv("GUILD"))

#embed builder
def create_team_embed(user: discord.abc.User, teams: list[str], team_map: dict = None):
    embed = discord.Embed(title="📢 Teams for the Event!", description="React with ✅ to join a team.", color=discord.Color.teal())
    embed.set_thumbnail(url="https://images4.alphacoders.com/112/1127690.png")
    embed.set_footer(text="You will be assigned randomly to one of the teams! :)")
    embed.set_author(name=user.name, icon_url=user.avatar.url if user.avatar else None)
    if team_map:
        for team in teams:
            count = len(team_map.get(team, []))
            embed.add_field(name=team, value=f"{count} member{'s' if count != 1 else ''}", inline=True)
    else:
        for team in teams:
            embed.add_field(name=team, value="0 members", inline=True)
    return embed

#slash cmd
@client.tree.command(name="team_assign", description="Assign teams to users via reaction", guild=GUILD_ID)
async def team_assign_slash(interaction: discord.Interaction):
    await interaction.response.send_message("Please enter team names (comma-separated)", ephemeral=True)

    def check(m):
        return m.author.id == interaction.user.id and m.channel == interaction.channel
    
    try:
        msg = await client.wait_for("message", timeout=60.0, check=check)
        teams = [t.strip() for t in msg.content.split(",") if t.strip()]
        if not teams:
            await interaction.followup.send("No valid teams provided", ephemeral=True)
            return
        
        channel = client.get_channel(int(os.getenv("CHANNEL_ID")))
        embed = create_team_embed(interaction.user, teams)
        sent = await channel.send(embed=embed)
        await sent.add_reaction("✅")

        #prepare internal state
        client.target_message_id = sent.id
        client.a1 = teams.copy()
        client.a2 = []
        client.team_map = {}

        guild = interaction.guild
        for team in teams:
            if not discord.utils.get(guild.roles, name=team):
                await guild.create_role(name=team)

        await interaction.followup.send("Team assignment embed sent!", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"Error: {e}", ephemeral=True)

#Prefix cmd
@client.command(name="team_assign")
async def team_assign_prefix(ctx: commands.Context):
    await ctx.send("Please enter team names (comma-seperated)")

    def check(m):
        return m.author.id == ctx.author.id and m.channel == ctx.channel

    try:
        msg = await client.wait_for("message", timeout=60.0, check=check)
        teams = [t.strip() for t in msg.content.split(",") if t.strip()]
        if not teams:
            await ctx.send("No valid teams provided")
            return
        
        channel = client.get_channel(int(os.getenv("CHANNEL_ID")))
        embed = create_team_embed(ctx.author, teams)
        sent = await channel.send(embed=embed)
        await sent.add_reaction("✅")

        #preparing internal state
        client.target_message_id = sent.id
        client.a1 = teams.copy()
        client.a2 = []
        client.team_map = {}

        guild = ctx.guild
        for team in teams:
            if not discord.utils.get(guild.roles, name=team):
                await guild.create_role(name=team)
            
        await ctx.send("Team assignment embed sent!")

    except Exception as e:
        await ctx.send(f"Error: {e}")

#bot run
discord_tok = os.getenv("DISCORD_TOKEN")
client.run(discord_tok)
