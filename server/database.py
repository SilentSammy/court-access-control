"""Shared MySQL connection helpers for the court access server."""

import math
import os
from datetime import datetime

import mysql.connector


DB_CONFIG = {
    "host": os.getenv("COURT_DB_HOST", "127.0.0.1"),
    "user": os.getenv("COURT_DB_USER", "root"),
    "password": os.getenv("COURT_DB_PASSWORD", ""),
    "database": os.getenv("COURT_DB_NAME", "squash_dk"),
}

CREDIT_VALUE = 150
MINUTES_PER_CREDIT = 30


def credits_for_minutes(minutes):
    """Return the whole credits charged for a play duration."""
    return math.ceil(minutes / MINUTES_PER_CREDIT)


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


def add_balance(user_id, amount, description='', timestamp=None):
    """Add a Pago activity for a database contact and return its activity ID."""
    conn = connect()
    cursor = conn.cursor()
    try:
        activity_time = timestamp or datetime.now()
        cursor.execute(
            """
            INSERT INTO actividades
                (contacto, fecha, `final`, tipo, valor, duracion, cancha, descripcion)
            VALUES (%s, %s, %s, 'Pago', %s, 0, 0, %s)
            """,
            (user_id, activity_time, activity_time, amount, description),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
