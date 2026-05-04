import csv
import os

# FILE_PATH is resolved relative to this file so the server can be run from any directory
_DIR = os.path.dirname(os.path.abspath(__file__))


class User:
    """Contains a user's id, and dynamically retrieves their credits and schedule."""

    def __init__(self, user_id: str):
        self.id = user_id

    @property
    def credits(self):
        """Returns the user's credits."""
        return UserManager.get_user(self.id)[1]  # also creates the user if new

    @credits.setter
    def credits(self, value: int):
        """Sets the user's credits."""
        UserManager.update_credits(self.id, value)

    @property
    def sessions(self):
        """Returns the user's booked sessions (as Session objects)."""
        from schedule import Schedule
        return [si.session for si in Schedule.get_user_schedule(self.id)]


class UserManager:
    FILE_PATH = os.path.join(_DIR, 'user.csv')
    _USERS: set = set()
    _LAST_UPDATE: float = 0

    @classmethod
    def _refresh_users(cls):
        """Read the users from the csv file and cache them."""
        with open(cls.FILE_PATH, 'r', newline='') as file:
            reader = csv.reader(file)
            cls._USERS = set((row[0], int(row[1])) for row in reader if row)

    @classmethod
    def get_users(cls):
        """Return the user list, refreshing from disk if the file has changed."""
        if not os.path.exists(cls.FILE_PATH):
            cls._USERS.clear()
        elif os.path.getmtime(cls.FILE_PATH) > cls._LAST_UPDATE:
            cls._LAST_UPDATE = os.path.getmtime(cls.FILE_PATH)
            cls._refresh_users()
        return list(cls._USERS)

    @classmethod
    def overwrite_users(cls):
        """Write the current in-memory user set to disk."""
        with open(cls.FILE_PATH, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerows(sorted(cls._USERS))  # sorted for deterministic output

    @classmethod
    def get_user(cls, user_id: str):
        """Return an existing user tuple, or create a new one with 0 credits."""
        users = cls.get_users()
        user = next((u for u in users if u[0] == user_id), None)
        if user:
            return user
        new_user = (user_id, 0)
        cls._USERS.add(new_user)
        cls.overwrite_users()
        return new_user

    @classmethod
    def pop_user(cls, user_id: str):
        """Remove a user from the in-memory set and persist."""
        user = cls.get_user(user_id)
        cls._USERS.discard(user)
        cls.overwrite_users()
        return user

    @classmethod
    def update_credits(cls, user_id: str, credits: int):
        """Update a user's credit balance."""
        cls.pop_user(user_id)
        cls._USERS.add((user_id, credits))
        cls.overwrite_users()


if __name__ == '__main__':
    import os, tempfile

    # ── Redirect storage to a temp file so the test is self-contained ──────────
    _orig_path = UserManager.FILE_PATH
    _tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w')
    _tmp.close()
    UserManager.FILE_PATH = _tmp.name
    UserManager._USERS.clear()
    UserManager._LAST_UPDATE = 0

    print("=== user.py tests ===")

    # 1. New user starts with 0 credits
    u = User('alice')
    assert u.credits == 0, f"Expected 0, got {u.credits}"
    print(f"[PASS] New user 'alice' has 0 credits")

    # 2. Credit assignment
    u.credits = 150
    assert u.credits == 150, f"Expected 150, got {u.credits}"
    print(f"[PASS] Set credits to 150")

    # 3. Credits persist after fresh User object
    u2 = User('alice')
    assert u2.credits == 150
    print(f"[PASS] Credits persist across User instances")

    # 4. Second user is independent
    b = User('bob')
    b.credits = 50
    assert User('alice').credits == 150
    assert User('bob').credits == 50
    print(f"[PASS] Multiple users are independent")

    # 5. get_users returns both
    all_users = UserManager.get_users()
    ids = [x[0] for x in all_users]
    assert 'alice' in ids and 'bob' in ids
    print(f"[PASS] get_users returns all users: {all_users}")

    # 6. pop_user removes correctly
    UserManager.pop_user('bob')
    ids = [x[0] for x in UserManager.get_users()]
    assert 'bob' not in ids
    print(f"[PASS] pop_user removes 'bob'")

    # Cleanup
    os.unlink(_tmp.name)
    UserManager.FILE_PATH = _orig_path

    print("\n=== All tests passed ===")
