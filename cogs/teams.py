import discord
from discord.ext import commands

class Teams(commands.Cog):
    """Handles team assignments and role management"""

    def __init__(self, bot):
        self.bot = bot

    def get_role(self, ctx, role_input):
        """Fetch a role only by mention (@RoleName)"""
        if role_input.startswith("<@&") and role_input.endswith(">"):
            role_id = int(role_input[3:-1])  # Extract ID from mention
            return discord.utils.get(ctx.guild.roles, id=role_id)
        return None  # Role must be mentioned

    def get_member(self, ctx, member_input):
        """Fetch a member only by mention (@UserName)"""
        if member_input.startswith("<@") and member_input.endswith(">"):
            member_id = int(member_input.replace("<@", "").replace(">", "").replace("&", ""))
            return ctx.guild.get_member(member_id)
        return None  # Member must be mentioned

    @commands.command(name="assign_team")
    @commands.has_permissions(manage_roles=True)
    async def assign_team(self, ctx, member_input: str = None, role_input: str = None):
        """
        Assigns a user to a specified team role.
        
        Usage: ?assign_team @User @RoleName
        - User must be mentioned (@User).
        - Role must be mentioned (@RoleName).
        - The bot must have permission to assign roles.
        - The role must exist in the server.
        - The user must not already have the role.
        """
        if not member_input or not role_input:
            await ctx.send("❌ **Incorrect usage!**\n"
                           "✅ Correct format: `?assign_team @User @RoleName`")
            return

        member = self.get_member(ctx, member_input)
        role = self.get_role(ctx, role_input)

        if member is None:
            await ctx.send("❌ **Invalid user!** You must mention a valid user (e.g., `@UserName`).")
            return

        if role is None:
            await ctx.send("❌ **Invalid role!** You must mention a valid role (e.g., `@RoleName`).")
            return

        if role in member.roles:
            await ctx.send(f"{member.mention} is already in {role.name}.")
            return

        try:
            await member.add_roles(role)
            await ctx.send(f"{member.mention} has been assigned to {role.name}.")
        except discord.Forbidden:
            await ctx.send("❌ **Permission error!** I don't have permission to assign this role.")
        except discord.HTTPException:
            await ctx.send("❌ **Error!** Failed to assign role due to a Discord API issue.")

    @commands.command(name="remove_team")
    @commands.has_permissions(manage_roles=True)
    async def remove_team(self, ctx, member_input: str = None, role_input: str = None):
        """
        Removes a specified team role from a user.
        
        Usage: ?remove_team @User @RoleName
        - User must be mentioned (@User).
        - Role must be mentioned (@RoleName).
        - The bot must have permission to remove roles.
        - The role must exist in the server.
        - The user must already have the role.
        """
        if not member_input or not role_input:
            await ctx.send("❌ **Incorrect usage!**\n"
                           "✅ Correct format: `?remove_team @User @RoleName`")
            return

        member = self.get_member(ctx, member_input)
        role = self.get_role(ctx, role_input)

        if member is None:
            await ctx.send("❌ **Invalid user!** You must mention a valid user (e.g., `@UserName`).")
            return

        if role is None:
            await ctx.send("❌ **Invalid role!** You must mention a valid role (e.g., `@RoleName`).")
            return

        if role not in member.roles:
            await ctx.send(f"{member.mention} is not in {role.name}.")
            return

        try:
            await member.remove_roles(role)
            await ctx.send(f"{member.mention} has been removed from {role.name}.")
        except discord.Forbidden:
            await ctx.send("❌ **Permission error!** I don't have permission to remove this role.")
        except discord.HTTPException:
            await ctx.send("❌ **Error!** Failed to remove role due to a Discord API issue.")


    

async def setup(bot):
    await bot.add_cog(Teams(bot))
