import sqlite3
from loguru import logger
from eth_account import Account
import time
import random
from utils.encryption import decrypt_data

@logger.catch
def get_db_connection(db_file):
    """
    Create a database connection to the SQLite database specified by db_file
    :param db_file: database file
    :return: Connection object
    """

    logger.debug("Connecting to {} db", db_file)
    return sqlite3.connect(db_file)

@logger.catch
def init_db(conn):
    cur = conn.cursor()
    logger.debug("Creating table 'accounts' and 'whitelist' if they don't exist.")
    cur.execute('''CREATE TABLE IF NOT EXISTS accounts (
                user_id INTEGER PRIMARY KEY,
                key TEXT NOT NULL UNIQUE
                )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS whitelist (
                user_id INTEGER PRIMARY KEY,
                address TEXT NOT NULL UNIQUE
                )''')
    conn.commit()
    cur.close()

@logger.catch
def get_db(db_file):
    logger.debug("Getting the {} database connection", db_file)
    conn = get_db_connection(db_file)
    init_db(conn)
    return conn

@logger.catch
def insert_account(conn, new_entry):
    """
    Insert a new (user_id, key) to the accounts table
    :param conn: Connection object
    :param new_entry: Tuple with (user_id (int), key (encrypted str))
    """
    logger.info("Inserting {} to db.", new_entry)
    query = '''INSERT INTO accounts (user_id,key) VALUES(?,?)'''
    cur = conn.cursor()
    cur.execute(query, new_entry)
    conn.commit()
    cur.close()

@logger.catch
def get_account_from_db(conn, user_id):
    """
    Get a user's account from the accounts table
    :param conn: Connection object
    :param user_id: Discord user id
    :return: Account object
    """

    logger.debug("Getting account from user {}.", user_id)
    cur = conn.cursor()
    cur.execute("SELECT key FROM accounts WHERE user_id=?", (user_id,))
    key = cur.fetchone()
    if not key:
        return None
    account = Account.from_key(decrypt_data(key[0]))

    cur.close()
    return account

@logger.catch
def insert_wl_address(conn, new_entry):
    """
    Insert a new (user_id, address) to the whitelist table
    :param conn: Connection object
    :param new_entry: Tuple with (user_id (int), address (str))
    """
    logger.info("Inserting {} to db.", new_entry)
    query = '''REPLACE INTO whitelist (user_id,address) VALUES(?,?)'''
    cur = conn.cursor()
    cur.execute(query, new_entry)
    conn.commit()

@logger.catch
def add_wl_addresses_to_db(conn, wl_addresses):
    """
    Insert multiple (null, address) to the whitelist table
    :param conn: Connection object
    :param wl_addresses: List of addresses (str)
    """
    values = [(random.randint(1, 9999999999999999), addr) for addr in wl_addresses]
    logger.info("Inserting {} to db.", values)
    query = '''INSERT OR IGNORE INTO whitelist (user_id,address) VALUES(?,?)'''
    cur = conn.cursor()
    cur.executemany(query, values)
    conn.commit()

@logger.catch
def get_wl_address_from_db(conn, user_id):
    """
    Get a user's account from the whitelist table
    :param conn: Connection object
    :param user_id: Discord user id
    :return: Account object
    """

    logger.debug("Getting address from user {}.", user_id)
    cur = conn.cursor()
    cur.execute("SELECT address FROM whitelist WHERE user_id=?", (user_id,))
    address = cur.fetchone()
    if not address:
        return None
    return address[0]

@logger.catch
def is_wl_address_in_db(conn, address):
    logger.debug("Searching address: {} in whitelist.", address)
    cur = conn.cursor()
    cur.execute("SELECT address FROM whitelist")
    addresses = cur.fetchall()
    return address in [addr[0] for addr in addresses]

@logger.catch
def get_whitelist(conn):
    """
    Get full list of addresses on the whitelist.
    :param conn: Connection object
    :return: file_path (str)
    """

    logger.debug("Getting all whitelist addresses")
    cur = conn.cursor()
    cur.execute("SELECT address FROM whitelist")
    addresses = cur.fetchall()
    wl_file = f"{int(time.time())}_whitelist.txt"
    logger.debug(f"Saving whitelist addresses to {wl_file}.")
    with open(wl_file, "w") as f:
        for addr in addresses:
            f.write(f"{addr[0]}\n")
    return wl_file
