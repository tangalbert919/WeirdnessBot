import discord
from discord.ext import commands
import json
import os
import asyncio
import asyncpg
from datetime import datetime
import random
import logging
import aiohttp
import traceback


class WeirdnessBot(commands.AutoShardedBot):

    def __init__(self):
        self.config = json.loads(open('config.json', 'r').read())
        self._prefix = self.config['prefix']
        super().__init__(command_prefix=self._prefix)
        self.remove_command('help')

        self.launch_time = datetime.utcnow()
        self.version_code = "Release 6 Beta"

        dbpass = self.config['dbpass']
        dbuser = self.config['dbuser']
        govinfo = {"user": dbuser, "password": dbpass, "database": "axiro", "host": "localhost", "max_size": 10}
        self.usedatabase = True

        async def _init_db():
            try:
                self.db = await asyncpg.create_pool(**govinfo)
                await self.db.execute(
                "CREATE TABLE IF NOT EXISTS users (id bigint primary key, name text, discrim varchar (4), money text);")
                await self.db.execute(
                "CREATE TABLE IF NOT EXISTS guilds (id bigint primary key, name text, prefix text);")
            except Exception:
                print("Database either not detected or initialized. Starting bot without database connection.")
                self.usedatabase = False

        self.loop.create_task(_init_db())

        self.status_msg = json.loads(open('status.json', 'r').read())
        self.loop.create_task(self.status_task())

        for file in os.listdir("modules"):
            if file.endswith(".py"):
                name = file[:-3]
                try:
                    self.load_extension(f"modules.{name}")
                except Exception:
                    print(f"The {name} module failed to load. Please repair it and load it.")

        logger = logging.getLogger('discord')
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
        handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
        logger.addHandler(handler)

    async def update_stats(self):
        """This function runs every 30 minutes to automatically update your server count"""
        while not self.is_closed():
            print('Attempting to post server count')
            dblload = json.dumps({
                'shard_count': self.shard_count,
                'server_count': len(self.guilds)
            })
            dblheaders = {
                'Authorization': self.config['dbl_token'],
                'Content-type': 'application/json'
            }
            dblurl = f'https://discordbots.org/api/bots/{self.user.id}/stats'

            async with aiohttp.ClientSession() as session:
                async with session.post(dblurl, data=dblload, headers=dblheaders) as resp:
                    data = await resp.json()
                    if data['error']:
                        print('The post failed. Please check your DBL key (unless you\'re testing the bot).')
                    else:
                         print('Posted server count ({})'.format(len(self.guilds)))
            await session.close()
            await asyncio.sleep(1800)

    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(name="x!help | Just started up!",
                                                             type=discord.ActivityType.playing))
        print('Logged in as ' + self.user.name + ' with id ' + str(self.user.id))
        self.loop.create_task(self.update_stats())
        app_info = await self.application_info()
        self.owner_id = app_info.owner.id

    async def on_message(self, message):
        if message.author == self.user:
            return
        if message.author.bot:
            return
        if not message.author.bot:
            if self.usedatabase:
                sql = "SELECT * FROM users WHERE id = $1"
                user = await self.db.fetchrow(sql, message.author.id)
                if not user:
                    add_user = "INSERT INTO users (id, name, discrim, money) VALUES ($1, $2, $3, 0);"
                    await self.db.execute(add_user, message.author.id, message.author.name,
                                          message.author.discriminator)
                else:
                    update_user = "UPDATE users SET name = $1, discrim = $2 WHERE id = $3"
                    await self.db.execute(update_user, message.author.name, message.author.discriminator,
                                          message.author.id)
        await self.process_commands(message)

    async def on_command_error(self, context, exception):
        if isinstance(exception, discord.ext.commands.errors.MissingRequiredArgument):
            await context.send("You're missing one or more required arguments.")
        elif isinstance(exception, discord.ext.commands.errors.BotMissingPermissions):
            await context.send("I am missing the required permissions to perform this command successfully.")
        elif isinstance(exception, discord.ext.commands.errors.MissingPermissions):
            await context.send("You do not have permission to perform this command.")
        elif isinstance(exception, discord.ext.commands.errors.CommandNotFound):
            pass
        elif isinstance(exception, discord.ext.commands.errors.BadArgument):
            await context.send("You used an invalid argument.")
        elif isinstance(exception, discord.ext.commands.errors.CommandOnCooldown):
            m, s = divmod(exception.retry_after, 60)
            h, m = divmod(m, 60)
            await context.send("Please slow down! (Rate-limited) :watch:\n"
                               "You can use this command in {} hours, {} minutes, and {} seconds."
                               .format(int(h), int(m), int(s)))
        elif isinstance(exception, discord.ext.commands.errors.NotOwner):
            await context.send("You must be the owner of the bot to use this command.")
        else:
            await context.send("An error has occurred, and has been reported to the developer.")
            c = self.get_channel(545462395296940063)
            await c.send(f'```py\n{exception}\n```')

    async def status_task(self):
        while not self.is_closed():
            selected = random.randint(1, 10)
            message = "x!help | " + self.status_msg.get(str(selected))
            await self.change_presence(activity=discord.Activity(name=message,
                                                                 type=discord.ActivityType.playing))
            await asyncio.sleep(300)

    async def on_guild_join(self, guild):
        if self.usedatabase:
            sql = "INSERT INTO guilds (id, name, prefix) VALUES ($1, $2, $3)"
            await self.db.execute(sql, guild.id, guild.name, "x!")
        channel = self.get_channel(477206313139699722)
        embed = discord.Embed(title="Guild joined!", color=discord.Colour.blue(),
                              description="We have joined a guild, bringing us to {} guilds!".format(len(self.guilds)))
        embed.add_field(name="Guild name:", value=guild.name)
        embed.add_field(name="Guild Owner: ", value=guild.owner)
        embed.add_field(name="Member count: ", value=guild.member_count)
        embed.set_thumbnail(url=guild.icon_url)
        await channel.send(embed=embed)

    async def on_guild_remove(self, guild):
        if self.usedatabase:
            sql = "DELETE FROM guilds where id = $1"
            await self.db.execute(sql, guild.id)
        channel = self.get_channel(477206313139699722)
        embed = discord.Embed(title="Guild lost!", color=discord.Colour.red(),
                              description="We have lost a guild, dropping us to {} guilds!".format(len(self.guilds)))
        embed.add_field(name="Guild name:", value=guild.name)
        embed.add_field(name="Guild Owner: ", value=guild.owner)
        embed.add_field(name="Member count: ", value=guild.member_count)
        embed.set_thumbnail(url=guild.icon_url)
        await channel.send(embed=embed)


client = WeirdnessBot()
config = json.loads(open('config.json', 'r').read())
client.run(config.get('discordtoken'))
