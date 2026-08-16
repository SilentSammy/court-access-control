"""Shared MySQL connection helpers for the court access server."""

import os

import mysql.connector


DB_CONFIG = {
    "host": os.getenv("COURT_DB_HOST", "127.0.0.1"),
    "user": os.getenv("COURT_DB_USER", "root"),
    "password": os.getenv("COURT_DB_PASSWORD", ""),
    "database": os.getenv("COURT_DB_NAME", "squash_dk"),
}

CREDIT_VALUE = 150


def connect(**kwargs):
    """Create a connection to the court database."""
    return mysql.connector.connect(**DB_CONFIG, **kwargs)


def get_contact_id(whatsapp_number):
    """Return the database contact ID for a WhatsApp number, or None."""
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM contactos WHERE whatsapp = %s",
            (str(whatsapp_number),),
        )
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()
        conn.close()
