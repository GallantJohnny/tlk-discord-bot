from loguru import logger
from web3 import Web3
from typing import Optional
import asyncio
import discord
from discord.ext import commands
from discord.utils import get
from utils.users import (get_address, get_user_balance, withdraw_to_address,
        tip_user)
# from tokens.tokens import tokens
from utils.utils import round_down, to_lower, get_min_gas
from utils.encryption import generate_key
from utils.fantom import verify_address
from database.database import (get_wl_address_from_db, insert_wl_address,
        get_whitelist, is_wl_address_in_db, add_wl_addresses_to_db)
from bot import errors, embeds
from bot.help import help_commands
from decimal import Decimal
from config import config

ADMINS = [687754112866975841, 303336238495039501, 205188831815794688,
        852094576784441365, 817156615840202775, 366965217621442561]

# LOSER WALDO 303336238495039501
# LOSER ROOT 205188831815794688
# LOSER KING 852094576784441365
# LOSER KRYPTONET 817156615840202775
# GallantJohny 366965217621442561 - !!! For Testing ONLY, REMOVE !!!

@logger.catch
def run_discord_bot(discord_token, conn, w3):
    command_prefix = "!"
    description = "TLK Bot, the bot of The Lost Kingdom."
    intents = discord.Intents().all()
    bot = commands.Bot(command_prefix=command_prefix,
                       intents=intents,
                       description=description,
                       help_command=None)

    ###
    # Help commands
    ###

    help_commands(bot)

    ###
    # Checks
    ###

    def is_admin(ctx):
        return ctx.message.author.id in ADMINS

    @bot.command(name="help-assign-role-to-early-users")
    @commands.check(is_admin)
    async def help_assign_role_to_early_users(ctx):
        logger.info("{} is executing !help-assign-role-to-early-users command.", ctx.author)
        await ctx.send(embed=embeds.help_assign_role_to_early_users())


    @bot.command(name="assign-role-to-early-users")
    @commands.check(is_admin)
    async def assign_role_to_early_users(ctx, number_of_users: int, channel: discord.TextChannel, role: discord.Role):
        logger.debug("{} is executing !assign-role-to-early-users command.", ctx.author)
        messages = await channel.history(limit=number_of_users, oldest_first=True).flatten()
        logger.info(str(role))
        users_for_wl = []

        for message in messages:
            if len(users_for_wl) < int(number_of_users):
                member = ctx.guild.get_member(message.author.id)
                if (member not in users_for_wl) and member is not None:
                    users_for_wl.append(member)

        for user in users_for_wl:
            if role not in user.roles:
                await user.add_roles(role)
            else:
                logger.debug("{} is already assigned to {}", role, user.name)

    @bot.command(name="help-admin")
    @commands.check(is_admin)
    async def help_admin(ctx):
        logger.info("{} is executing !help-admin command.", ctx.author)
        await ctx.send(embed=embeds.help_admin())

    ###
    # Tip bot commands
    ###

    @bot.command()
    @commands.check(is_admin)
    async def whitelist(ctx, *, receiver: discord.Member):
        logger.debug("{} is executing !whitelist command.", ctx.author)
        wl_role = get(ctx.guild.roles, id=int(config["WHITELIST_ROLE_ID"]))
        logger.debug("Whitelist role: {}", wl_role)
        if wl_role in receiver.roles:
            return await ctx.send(embed=errors.handle_already_on_whitelist(receiver))
        await receiver.add_roles(wl_role)
        await ctx.send(embed=embeds.whitelist_successful(receiver))
        # dm_channel = await receiver.create_dm()
        # await dm_channel.send(embed=embeds.whitelist_verify_prompt())

    @bot.command(name="whitelist-multi")
    @commands.check(is_admin)
    async def whitelist_multi(ctx, *args):
        logger.debug("{} is executing !whitelist-multi command.", ctx.author)
        wl_role = get(ctx.guild.roles, id=int(config["WHITELIST_ROLE_ID"]))
        logger.debug("Whitelist role: {}", wl_role)
        for x in args:
            try:
                receiver_id = int(x.strip("<@!>"))
            except ValueError:
                receiver_id = -1
            receiver = ctx.guild.get_member(receiver_id)
            if not receiver:
                continue
            if wl_role in receiver.roles:
                await ctx.send(embed=errors.handle_already_on_whitelist(receiver))
            else:
                await receiver.add_roles(wl_role)
                await ctx.send(embed=embeds.whitelist_successful(receiver))
        # dm_channel = await receiver.create_dm()
        # await dm_channel.send(embed=embeds.whitelist_verify_prompt())

    @bot.command(name="whitelist-address")
    @commands.check(is_admin)
    @commands.dm_only()
    async def whitelist_address(ctx):
        logger.debug("{} is executing !whitelist-address command.", ctx.author)

        def is_valid(msg):
            return msg.channel == ctx.channel and msg.author == ctx.author

        counter = 0
        wl_addresses = []
        while counter < 100:
            await ctx.send(embed=embeds.wl_address_prompt())
            address = await bot.wait_for("message", check=is_valid)
            address = address.content

            if address.lower() == "done":
                break
            elif Web3.isAddress(address):
                wl_addresses.append(address)
                counter += 1
            else:
                await ctx.send(embed=errors.handle_invalid_wl_address())
        if len(wl_addresses) > 0:
            await ctx.send(embed=embeds.wl_address_ok_prompt(wl_addresses))
            confirmation = await bot.wait_for("message", check=is_valid)
            if confirmation.content.lower() in ["yes", "y", "confirm"]:
                add_wl_addresses_to_db(conn, wl_addresses)
                await ctx.send(embed=embeds.wl_address_success())
            else:
                await ctx.send(embed=embeds.wl_address_cancelled())
        else:
            await ctx.send(embed=errors.handle_empty_wl_address())

    @bot.command()
    @commands.dm_only()
    async def verify(ctx):
        logger.debug("{} is executing !verify command.", ctx.author)
        tlk_guild = bot.get_guild(int(config["GUILD_ID"]))
        wl_role = get(tlk_guild.roles, id=int(config["WHITELIST_ROLE_ID"]))
        member = tlk_guild.get_member(ctx.author.id)
        if wl_role not in member.roles:
            # return await ctx.send(embed=errors.handle_not_on_whitelist())
            return await ctx.send(embed=errors.handle_nothing_to_do())
        def is_valid(msg):
            return msg.channel == ctx.channel and msg.author == ctx.author

        address = get_wl_address_from_db(conn, ctx.author.id)
        if address:
            await ctx.send(embed=embeds.existing_address_prompt(address))
            change_address = await bot.wait_for("message", check=is_valid)
            if change_address.content.lower() not in ["yes", "y", "confirm"]:
                return await ctx.send(embed=embeds.address_not_changed())

        await ctx.send(embed=embeds.wallet_address_prompt())
        address = await bot.wait_for("message", check=is_valid)
        address = address.content

        if not Web3.isAddress(address):
            return await ctx.send(embed=errors.handle_invalid_address())

        key = generate_key()
        await ctx.send(embed=embeds.verify_ftmscan_instructions(key))
        confirmation = await bot.wait_for("message", check=is_valid)
        if confirmation.content.lower() == "cancel":
            return await ctx.send(embed=embeds.verification_cancelled())
        await ctx.send(embed=embeds.verification_in_progress())
        for i in range(10):
            if verify_address(w3, address, key):
                insert_wl_address(conn, (ctx.author.id, address))
                return await ctx.send(embed=embeds.verification_confirmed(address))
            await asyncio.sleep(60)
        await ctx.send(embed=errors.verification_timeout())

    @bot.command(name="check-whitelist")
    @commands.dm_only()
    async def check_whitelist(ctx, *, address: Optional[str]):
        logger.debug("{} is executing !check-whitelist command.", ctx.author)
        def is_valid(msg):
            return msg.channel == ctx.channel and msg.author == ctx.author

        tlk_guild = bot.get_guild(int(config["GUILD_ID"]))
        wl_role = get(tlk_guild.roles, id=int(config["WHITELIST_ROLE_ID"]))
        member = tlk_guild.get_member(ctx.author.id)
        if wl_role not in member.roles:
            await ctx.send(embed=embeds.wallet_address_prompt())
            address = await bot.wait_for("message", check=is_valid)
            address = address.content
            if not Web3.isAddress(address):
                return await ctx.send(embed=errors.handle_invalid_address())
            if is_wl_address_in_db(conn, address):
                return await ctx.send(embed=embeds.address_in_whitelist(address))
            else:
                return await ctx.send(embed=errors.handle_not_on_whitelist())

        address = get_wl_address_from_db(conn, ctx.author.id)
        if address:
            await ctx.send(embed=embeds.address_in_whitelist(address))
        else:
            await ctx.send(embed=embeds.address_verification_needed())


    @bot.command(name="show-whitelist")
    @commands.check(is_admin)
    @commands.dm_only()
    async def show_whitelist(ctx):
        logger.debug("{} is executing !show-whitelist command.", ctx.author)
        wl_file = get_whitelist(conn)
        await ctx.send(file=discord.File(wl_file))

    # @bot.command()
    # @commands.check(is_admin)
    # async def gas(ctx, gas_price: int):
        # config["GAS_PRICE"] = gas_price
        # await ctx.send(embed=embeds.set_gas(gas_price))

    # @bot.command(name="tokens")
    # async def _tokens(ctx):
        # logger.debug("Executing $tokens command.")
        # await ctx.send(embed=embeds.list_tokens(tokens))

    # @bot.command(name="d")
    # @commands.dm_only()
    # async def deposit(ctx, device: Optional[str]):
        # logger.debug("Executing $deposit command.")
        # address = get_address(conn, ctx.author)
        # if device == "mobile":
            # await ctx.send(embed=embeds.deposit_address_mobile(address))
            # await ctx.send(f"{address}")
        # else:
            # await ctx.send(embed=embeds.deposit_address(address))

    # @bot.command(name='w')
    # @commands.dm_only()
    # async def withdraw(ctx, *, token: to_lower):
        # logger.debug("Executing $withdraw command.")
        # if token not in tokens:
            # return await ctx.send(embed=errors.handle_invalid_token())

        # balance = get_user_balance(conn, w3, ctx.author, token)
        # if balance == 0:
            # return await ctx.send(embed=errors.handle_no_funds(token))

        # ftm_balance = get_user_balance(conn, w3, ctx.author, "ftm")
        # min_gas = get_min_gas(w3)
        # if ftm_balance < min_gas * 2: # enough gas for 2 transactions
            # return await ctx.send(embed=errors.handle_not_enough_gas(min_gas*2))

        # def is_valid(msg):
            # return msg.channel == ctx.channel and msg.author == ctx.author

        # await ctx.send(embed=embeds.dst_address_prompt(token))
        # address = await bot.wait_for("message", check=is_valid)
        # address = address.content

        # if address == "cancel":
            # await ctx.send(embed=embeds.withdrawal_cancelled())
        # elif not Web3.isAddress(address):
            # await ctx.send(embed=errors.handle_invalid_address())
        # else:
            # await ctx.send(embed=embeds.withdrawal_amount_prompt(balance, token))
            # amount = await bot.wait_for("message", check=is_valid)
            # if amount.content.lower() == "cancel":
                # return await ctx.send(embed=embeds.withdrawal_cancelled())
            # if amount.content.lower() == "all":
                # _amount = Decimal(balance)
            # else:
                # try:
                    # _amount = Decimal(amount.content)
                # except:
                    # return await ctx.send(embed=errors.handle_invalid_amount())

            # if token == "ftm":
                # _amount -= min_gas * 2 # To cover for gas fees
            # fee = round_down(_amount * Decimal(config["FEE"]), 6)
            # _amount -= fee
            # if _amount < Decimal("1e-6"):
                # return await ctx.send(embed=errors.handle_withdrawal_too_small())
            # total = _amount + fee
            # if token == "ftm":
                # total += min_gas * 2
            # if 0 < total <= balance:
                # await ctx.send(embed=embeds.withdrawal_ok_prompt(_amount, token,
                            # address, fee))
                # confirmation = await bot.wait_for("message", check=is_valid)
                # if confirmation.content.lower() in ["yes", "y", "confirm"]:
                    # main_txn, fee_txn = withdraw_to_address(conn, w3,
                            # ctx.author, token, _amount, address, fee)
                    # if main_txn == None:
                        # return await ctx.send(embed=errors.handle_unknown_error())
                    # await ctx.send(embed=embeds.withdrawal_successful(_amount,
                        # fee, token, address, main_txn, fee_txn))
                # else:
                    # await ctx.send(embed=embeds.withdrawal_cancelled())
            # else:
                # await ctx.send(embed=errors.handle_insufficient_balance(_amount,
                    # token, balance))

    # @bot.command(name='b')
    # async def balance(ctx, *, token: to_lower):
        # logger.debug("Executing $balance command.")
        # if token not in tokens:
            # return await ctx.send(embed=errors.handle_invalid_token())
        # balance = get_user_balance(conn, w3, ctx.author, token)
        # await ctx.send(embed=embeds.show_balance(ctx, balance, token))

    # @bot.command(name='t')
    # async def tip(ctx, receiver: discord.Member, amount: Decimal, *, token: to_lower):
        # logger.debug("Executing $tip command.")
        # if amount < Decimal("1e-6"):
            # return await ctx.send(embed=errors.handle_tip_too_small())
        # if token not in tokens:
            # return await ctx.send(embed=errors.handle_invalid_token())

        # balance = get_user_balance(conn, w3, ctx.author, token)
        # if amount > balance:
            # return await ctx.send(embed=errors.handle_insufficient_balance(
                # amount, token, balance))
        # min_gas = get_min_gas(w3)

        # if token == "ftm":
            # if amount + min_gas > balance:
                # return await ctx.send(embed=errors.handle_not_enough_gas(min_gas))
        # else:
            # ftm_balance = get_user_balance(conn, w3, ctx.author, "ftm")
            # if ftm_balance < min_gas:
                # return await ctx.send(embed=errors.handle_not_enough_gas(min_gas))

        # txn_hash = tip_user(conn, w3, ctx.author, receiver, amount, token)
        # if not txn_hash:
            # return await ctx.send(embed=errors.handle_unknown_error())
        # await ctx.send(embed=embeds.tip_succesful(ctx.author, receiver, amount,
            # token, txn_hash))

    ###
    # Command Errors
    ###

    @help_admin.error
    async def help_admin_error(ctx, error):
        logger.error("{}: {} User: {}", type(error).__name__, error, ctx.author)
        await ctx.send(embed=errors.handle_admin_only(error))

    @whitelist.error
    async def whitelist_error(ctx, error):
        try:
            receiver = ctx.kwargs["receiver"]
        except KeyError:
            receiver = None
        logger.error("{}: {} User: {}", type(error).__name__, error, ctx.author)
        await ctx.send(embed=errors.handle_whitelist(error, receiver))

    @whitelist_multi.error
    async def whitelist_multi_error(ctx, error):
        logger.error("{}: {} User: {}", type(error).__name__, error, ctx.author)
        await ctx.send(embed=errors.handle_admin_only(error))

    @whitelist_address.error
    async def whitelist_address_error(ctx, error):
        logger.error("{}: {} User: {}", type(error).__name__, error, ctx.author)
        await ctx.send(embed=errors.handle_whitelist_address(error))

    @verify.error
    async def verify_error(ctx, error):
        logger.error("{}: {} User: {}", type(error).__name__, error, ctx.author)
        await ctx.send(embed=errors.handle_dm_only(error))

    @check_whitelist.error
    async def check_whitelist_error(ctx, error):
        logger.error("{}: {} User: {}", type(error).__name__, error, ctx.author)
        await ctx.send(embed=errors.handle_dm_only(error))

    @show_whitelist.error
    async def show_whitelist_error(ctx, error):
        logger.error("{}: {} User: {}", type(error).__name__, error, ctx.author)
        await ctx.send(embed=errors.handle_show_whitelist(error))

    # @gas.error
    # async def gas_error(ctx, error):
        # logger.error("{}: {}", type(error).__name__, error)
        # await ctx.send(embed=errors.handle_not_admin())

    # @deposit.error
    # async def deposit_error(ctx, error):
        # logger.error("{}: {}", type(error).__name__, error)
        # await ctx.send(embed=errors.handle_deposit(error))

    # @withdraw.error
    # async def withdraw_error(ctx, error):
        # logger.error("{}: {}", type(error).__name__, error)
        # await ctx.send(embed=errors.handle_withdrawal(error))

    # @balance.error
    # async def balance_error(ctx, error):
        # logger.error("{}: {}", type(error).__name__, error)
        # await ctx.send(embed=errors.handle_balance(error))

    # @tip.error
    # async def tip_error(ctx, error):
        # logger.error("{}: {}", type(error).__name__, error)
        # await ctx.send(embed=errors.handle_tipping(error))

    ###
    # Run Bot
    ###

    @bot.listen
    async def on_message(message):
        await bot.process_commands(message)

    @bot.event
    async def on_ready():
        logger.info("Bot {} is ready!", bot.user)

    bot.run(discord_token)
