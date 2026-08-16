from server.schedule import GlobalSchedule
from server.database import connect


class User:
    """Contains a user's id, and dynamically retrieves their credits and schedule."""

    def __init__(self, user_id: str, schedule: GlobalSchedule):
        self.id = user_id
        self.schedule = schedule

    @property
    def credits(self):
        """Returns the user's credits."""
        return UserManager.get_user(self.id)[1]

    @credits.setter
    def credits(self, value: int):
        """Credit updates are not supported by the current database schema."""
        UserManager.update_credits(self.id, value)

    @property
    def sessions(self):
        """Returns the user's booked sessions (as Session objects)."""
        gs = self.schedule  
        return [si.session for si in gs.get_user_schedule(self.id)]


class UserManager:
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
            return [(str(whatsapp), credits) for whatsapp, credits in cursor.fetchall()]
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
            return (str(row[0]), row[1]) if row else (str(user_id), 0)
        finally:
            cursor.close()
            conn.close()

    @classmethod
    def pop_user(cls, user_id: str):
        """No-op: deleting contacts is outside this application's scope."""
        return cls.get_user(user_id)

    @classmethod
    def update_credits(cls, user_id: str, credits: int):
        """No-op until the database has an explicit balance-update workflow."""
        return None
