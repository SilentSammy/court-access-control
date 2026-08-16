from decimal import Decimal

from server.schedule import GlobalSchedule
from server.database import CREDIT_VALUE, add_balance, connect, get_contact_id


class User:
    """Contains a user's id, and dynamically retrieves their credits and schedule."""

    def __init__(self, user_id: str, schedule: GlobalSchedule):
        self.id = user_id
        self.schedule = schedule

    @property
    def credits(self):
        """Returns the user's credits."""
        return self.balance / CREDIT_VALUE

    @property
    def balance(self):
        """Return the user's monetary balance from database activities."""
        return UserManager.get_user_balance(self.id)

    @balance.setter
    def balance(self, value):
        """Set the user's balance in pesos using a Pago adjustment."""
        UserManager.update_balance(self.id, value)

    @property
    def name(self):
        """Return the user's database name, falling back to their ID."""
        return UserManager.get_user_name(self.id) or self.id

    @credits.setter
    def credits(self, value):
        """Set credits by recording the required balance adjustment."""
        UserManager.update_credits(self.id, value)

    @property
    def sessions(self):
        """Returns the user's booked sessions (as Session objects)."""
        gs = self.schedule  
        return [si.session for si in gs.get_user_schedule(self.id)]


class UserManager:
    @classmethod
    def get_user_name(cls, user_id: str):
        """Return the contact name for a WhatsApp number, or None."""
        conn = connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT nombre FROM contactos WHERE whatsapp = %s",
                (str(user_id),),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            cursor.close()
            conn.close()

    @classmethod
    def get_user_balance(cls, user_id: str):
        """Return the raw Pago-minus-Rent monetary balance for a user."""
        conn = connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT COALESCE(SUM(CASE
                           WHEN a.tipo = 'Pago' THEN a.valor
                           WHEN a.tipo = 'Rent' THEN -a.valor
                           ELSE 0
                       END), 0) AS balance
                FROM contactos AS c
                LEFT JOIN actividades AS a ON a.contacto = c.id
                WHERE c.whatsapp = %s
                GROUP BY c.id
                """,
                (str(user_id),),
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            cursor.close()
            conn.close()

    @classmethod
    def get_users(cls):
        """Return ``(whatsapp, credits)`` tuples for all database users."""
        conn = connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT c.whatsapp,
                       COALESCE(SUM(CASE
                           WHEN a.tipo = 'Pago' THEN a.valor
                           WHEN a.tipo = 'Rent' THEN -a.valor
                           ELSE 0
                       END), 0) AS credits
                FROM contactos AS c
                LEFT JOIN actividades AS a ON a.contacto = c.id
                GROUP BY c.id, c.whatsapp
                """
            )
            return [
                (str(whatsapp), balance / CREDIT_VALUE)
                for whatsapp, balance in cursor.fetchall()
            ]
        finally:
            cursor.close()
            conn.close()

    @classmethod
    def overwrite_users(cls):
        """No-op: users are managed by the existing contactos table."""
        return None

    @classmethod
    def get_user(cls, user_id: str):
        """Return a user's ``(whatsapp, credits)`` tuple.

        Unknown WhatsApp numbers are not inserted into ``contactos`` and are
        represented with a zero balance.
        """
        conn = connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT c.whatsapp,
                       COALESCE(SUM(CASE
                           WHEN a.tipo = 'Pago' THEN a.valor
                           WHEN a.tipo = 'Rent' THEN -a.valor
                           ELSE 0
                       END), 0) AS credits
                FROM contactos AS c
                LEFT JOIN actividades AS a ON a.contacto = c.id
                WHERE c.whatsapp = %s
                GROUP BY c.id, c.whatsapp
                """,
                (str(user_id),),
            )
            row = cursor.fetchone()
            return (
                (str(row[0]), row[1] / CREDIT_VALUE)
                if row else (str(user_id), 0)
            )
        finally:
            cursor.close()
            conn.close()

    @classmethod
    def pop_user(cls, user_id: str):
        """No-op: deleting contacts is outside this application's scope."""
        return cls.get_user(user_id)

    @classmethod
    def update_credits(cls, user_id: str, credits):
        """Set credits by adding the missing amount as a Pago activity."""
        target_balance = Decimal(str(credits)) * Decimal(CREDIT_VALUE)
        return cls.update_balance(user_id, target_balance)

    @classmethod
    def update_balance(cls, user_id: str, balance):
        """Set a peso balance by adding the missing amount as a Pago activity."""
        contact_id = get_contact_id(user_id)
        if contact_id is None:
            raise ValueError(f"No database contact found for WhatsApp number {user_id}")

        current_balance = Decimal(str(cls.get_user_balance(user_id)))
        target_balance = Decimal(str(balance))
        missing_amount = target_balance - current_balance

        if missing_amount == 0:
            return None

        return add_balance(
            contact_id,
            missing_amount,
            description='Balance adjustment',
        )
