import discord
from io import BytesIO
from discord.ext import commands
from ext.checks import mod_check


class TicketCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.log_channel = 736545547112022036  # log channel id here
        self.log_category = 736545513092153405  # category id under which the channel will be created
        self.mod_role = 633141294633451540  # mod role id
        self.txt_channel = 736569881494814730
        self.unapproved = 0x1cc1e6
        self.awaiting_fixes = 0xf73538
        self.colour = 0x1cc1e6
        self.closed_ticket_col = 0xe40707

    def feedback_moderator():
        async def predicate(ctx):
            owner = await ctx.bot.db.statuses.find_one({"channel_id": str(ctx.channel.id)})
            if owner['owner_id'] == str(ctx.author.id):
                return True
            elif owner['owner_id'] != str(ctx.author.id):
                await ctx.send(f"You can't take over this approval feedback!")
                return False
            return False

        return commands.check(predicate)

    async def ticket_opened(self, ctx, mod=None, channel=None, message=None, reason=None):
        e = discord.Embed(color=self.colour, title=f"Approval ticket")
        e.description = reason
        e.set_footer(text=f"STATUS: Waiting for Response")
        e.add_field(name=f"Channel:",
                    value=f"{ctx.guild.get_channel(channel).mention}\n#{ctx.guild.get_channel(channel)}")
        logchannel = ctx.guild.get_channel(self.log_channel)
        logged_msg = await logchannel.send(embed=e)
        await self.bot.db.statuses.insert_one(
            {'channel_id': str(channel), 'message_id': str(message), 'owner_id': str(mod),
             'log_msg_id': str(logged_msg.id),
             'feedback_status': 0, 'closure_reason': None})

    async def ticket_awaiting(self, ctx, message=None):
        logmsg = await ctx.bot.db.statuses.find_one({"message_id": str(message)})
        msg = await ctx.guild.get_channel(self.log_channel).fetch_message(logmsg)
        embed = msg.embeds[0]
        embed.color = self.awaiting_fixes
        embed.set_footer(text="STATUS: Awaiting Fixes")
        await msg.edit(embed=embed)
        await ctx.bot.db.statuses.update_one({"channel_id": str(ctx.channel.id)}, {
            "$set": {
                'feedback_status': 1
            }
        })

    async def ticket_closed(self, ctx, channel=None, reason=None, file=None):
        logmsg = await self.bot.db.statuses.find_one({"channel_id": str(channel)})
        msg = await ctx.guild.get_channel(self.log_channel).fetch_message(logmsg['log_msg_id'])
        msg_history = await ctx.guild.get_channel(self.txt_channel).send(content=msg.jump_url, file=file)
        embed = msg.embeds[0]
        embed.color = self.closed_ticket_col
        embed.add_field(name='Reason:', value=reason, inline=False)
        embed.add_field(name='Moderator', value=f"{ctx.author} ({ctx.author.id})")
        embed.add_field(name="Channel message history:", value=f"[Jump to file]({msg_history.jump_url})")
        embed.set_footer(text="STATUS: Closed")
        await msg.edit(embed=embed)
        await ctx.bot.db.statuses.update_one({"channel_id": str(channel)}, {
            "$set": {
                'feedback_status': 2,
                'closure_reason': reason
            }
        })

    async def ownership_transfered(self, ctx, old_mod=None, new_mod=None):
        await ctx.bot.db.statuses.update_one({"channel_id": str(ctx.channel.id)}, {
            "$set": {
                'owner_id': new_mod.id
            }
        })
        msgid = await ctx.bot.db.statuses.find_one({'channel_id': str(ctx.channel.id)})
        channel = ctx.guild.get_channel(self.log_channel)
        msg = await channel.fetch_message(msgid['log_msg_id'])
        e = discord.Embed(color=self.colour, title="Ownership transferred!")
        e.description = f"**{old_mod}** has transfered {ctx.channel} ownership to **{new_mod}**.\n[Approval feedback " \
                        f"status]({msg.jump_url}) "
        await channel.send(embed=e)

    @commands.command(name="open-ticket")
    @commands.guild_only()
    @mod_check()
    async def open_ticket(self, ctx, bot: discord.User, member: discord.Member, *, issues: str):

        if len(issues) > 1900:
            return await ctx.send(
                f"Sorry, the issue is way too long! {len(issues)}/1900 chars, please open the ticket and write the "
                f"issues yourself.")
        if not bot.bot:
            return await ctx.send(f"{bot} is not a bot!")
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            ctx.author: discord.PermissionOverwrite(read_messages=True)
        }
        for channel in ctx.guild.channels:
            if channel.name == f"{bot.name.lower()}-approval-feedback":
                return await ctx.send(f"{channel.mention} is already created for that bot!")
        try:
            category = ctx.guild.get_channel(self.log_category)
            channel = await ctx.guild.create_text_channel(name=f'{bot.name}-approval-feedback', overwrites=overwrites,
                                                          category=category,
                                                          reason=f"[ Mod: {ctx.author} ({ctx.author.id}) ] approval "
                                                                 f"feedback channel")
            e = discord.Embed(color=self.unapproved, title=f"Approval-feedback regarding your bot {bot}")
            e.description = f"**Hello, {member.name}, while reviewing your bot we found few issues that should get " \
                            f"fixed.\nHere are the issues we found:**\n {issues} "
            e.set_footer(text='FEEDBACK STATUS: Waiting for Response')
            msg = await channel.send(content=member.mention, embed=e,
                                     allowed_mentions=discord.AllowedMentions(users=True))
            await msg.pin()
            await self.ticket_opened(ctx, channel=channel.id, message=msg.id, reason=issues, mod=ctx.author.id)
            await ctx.send(f"{channel.mention} was created successfully and owner informed!", delete_after=20)
        except Exception as e:
            await ctx.send(f"Something failed! Error information: `{e}`")

    @commands.command(name='awaiting-fixes')
    @commands.guild_only()
    @mod_check()
    @feedback_moderator()
    async def awaiting_fixes(self, ctx):
        status_check = await ctx.bot.db.statuses.find_one({'channel_id': str(ctx.channel.id)})
        await ctx.message.delete()

        if status_check and status_check['feedback_status'] == 0:
            message = await ctx.channel.fetch_message(int(status_check['message_id']))
            embed = message.embeds[0]
            embed.color = self.awaiting_fixes
            embed.set_footer(text="FEEDBACK STATUS: Awaiting Fixes")
            await message.edit(embed=embed)
            msg = await ctx.send("Feedback marked as `Awaiting Fixes`")
            await self.ticket_awaiting(ctx, message=message.id)
        elif not status_check:
            return await ctx.send("This doesn't look like a approval-feedback channel.", delete_after=20)
        elif status_check and status_check == 1:
            return await ctx.send("Feedback already marked as Awaiting Fixes.", delete_after=20)
        else:
            return

    @commands.command(name='close-ticket')
    @commands.guild_only()
    @mod_check()
    @feedback_moderator()
    async def close_ticket(self, ctx, *, reason: str):
        messageid = await ctx.bot.db.statuses.find_one({"channel_id": str(ctx.channel.id)})
        if len(reason) > 1000:
            return await ctx.send(
                f"Reason is too long... In fact, why do you need to make it longer than 1000 chars. ({len(reason)}/1000)",
                delete_after=20)
        if messageid:
            logchannel = ctx.guild.get_channel(self.log_channel)
            msgs = []
            for message in await ctx.channel.history().flatten():
                msgs.append(f"[{message.created_at}] {message.author} - {message.content}\n")
            msgs.reverse()
            msgshis = "".join(msgs)
            data = BytesIO(msgshis.encode('utf-8'))
            file = discord.File(data, filename=f"{messageid['_id']}.txt")
            await ctx.channel.delete(reason=f"[ Mod: {ctx.author} ({ctx.author.id}) ] {reason}")
            await self.ticket_closed(ctx, channel=ctx.channel.id, reason=reason, file=file)
        elif not messageid:
            return await ctx.send(f"That doesn't look like a approval-feedback channel.", delete_after=20)

    @commands.command(name='transfer-ticket')
    @commands.guild_only()
    @mod_check()
    @feedback_moderator()
    async def transfer_ticket(self, ctx, moderator: discord.Member):
        owner = await ctx.bot.db.statuses.find_one({"channel_id": str(ctx.channel.id)})

        role = ctx.guild.get_role(self.mod_role)
        if role not in moderator.roles:
            return await ctx.send("You cannot transfer the ownership to non-moderator.")
        elif role in moderator.roles:
            if owner['owner_id'] == moderator.id:
                return await ctx.send(
                    "Why the heck are you trying to transfer it to yourself? You're already an owner.")
            elif owner['owner_id'] != moderator.id:
                await self.ownership_transfered(ctx, old_mod=ctx.author, new_mod=moderator)
                try:
                    await moderator.send(f"{ctx.author} transfered {ctx.channel.mention} ownership to you!")
                except:
                    pass
                await ctx.send(f"This approval feedback was successfully transfered to {moderator.mention}")
                if ctx.channel.overwrites_for(moderator).send_messages == (False or None):
                    await ctx.channel.set_permissions(moderator, read_messages=True, send_messages=True,
                                                      read_message_history=True,
                                                      reason=f"[ Mod: {ctx.author} ({ctx.author.id}) ] Feedback "
                                                             f"ownership transfered")
                    await ctx.channel.set_permissions(ctx.author, read_messages=False,
                                                      reason=f"[ Mod: {ctx.author} ({ctx.author.id}) ] Feedback "
                                                             f"ownership transfered")
                else:
                    return

    @commands.command(name='add-moderator')
    @commands.guild_only()
    @mod_check()
    @feedback_moderator()
    async def add_moderator(self, ctx, moderator: discord.Member):
        role = ctx.guild.get_role(self.mod_role)
        if role not in moderator.roles:
            return await ctx.send("You cannot add a non-moderator!")
        elif role in moderator.roles:
            if ctx.author.id == moderator.id:
                return await ctx.send("Why the heck are you trying to add yourself, you're already added.")
            elif ctx.author.id != moderator.id:
                if ctx.channel.overwrites_for(moderator).send_messages == (False or None):
                    await ctx.channel.set_permissions(moderator, read_messages=True, send_messages=True,
                                                      read_message_history=True,
                                                      reason=f"[ Mod: {ctx.author} ({ctx.author.id}) ] Added to "
                                                             f"approval feedback")
                    try:
                        await moderator.send(f"{ctx.author} added you to {ctx.channel.mention} approval feedback!")
                    except:
                        pass
                    await ctx.send(f"Added {moderator.mention} to this approval feedback")
                else:
                    await ctx.send(f"{moderator} is already added to this approval feedback")

    @commands.command(name='remove-moderator')
    @commands.guild_only()
    @mod_check()
    @feedback_moderator()
    async def remove_moderator(self, ctx, moderator: discord.Member):

        role = ctx.guild.get_role(self.mod_role)
        if role not in moderator.roles:
            return await ctx.send("You cannot remove a non-moderator!")
        elif role in moderator.roles:
            if ctx.author.id == moderator.id:
                return await ctx.send(
                    "If you want to remove yourself, just transfer the ownership of this approval feedback to another "
                    "moderator")
            elif ctx.author.id != moderator.id:
                if ctx.channel.overwrites_for(moderator).send_messages:
                    await ctx.channel.set_permissions(moderator, read_messages=False, send_messages=False,
                                                      read_message_history=False,
                                                      reason=f"[ Mod: {ctx.author} ({ctx.author.id}) ] Removed from "
                                                             f"approval feedback")
                    await ctx.send(f"Removed {moderator.mention} from this approval feedback")
                    try:
                        await moderator.send(f"{ctx.author} removed you from {ctx.channel.mention} approval feedback!")
                    except:
                        pass
                elif ctx.channel.overwrites_for(moderator).send_messages == (False or None):
                    await ctx.send(f"{moderator} is not added to this approval feedback yet.")


def setup(bot):
    bot.add_cog(TicketCog(bot))