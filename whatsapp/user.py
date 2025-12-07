import csv
import os
from schedule import Schedule, ScheduleItem

class User:
    """Contains a user's id, and dynamically retrieves their credits and schedule"""

    def __init__(self, user_id:str):
        self.id = user_id
    
    @property
    def credits(self):
        """Returns the user's credits"""
        return UserManager.get_user(self.id)[1] # this will also create the user if it doesn't exist
    
    @credits.setter
    def credits(self, value:int):
        """Sets the user's credits"""
        UserManager.update_credits(self.id, value)
    
    @property
    def sessions(self):
        """Returns the user's schedule"""
        return [si.session for si in Schedule().get_user_schedule(self.id)]

class UserManager:
    FILE_PATH = 'user.csv'
    _USERS = set()
    _LAST_UPDATE = 0

    @classmethod
    def _refresh_users(cls):
        """Read the users from the csv file and store them in the users set"""
        with open(cls.FILE_PATH, 'r') as file:
            reader = csv.reader(file)
            cls._USERS = set([(row[0], int(row[1])) for row in reader if row])

    @classmethod
    def get_users(cls):
        """Returns the users set, refreshing it if the file has been updated"""
        
        # check if the file exists and has been updated
        if not os.path.exists(cls.FILE_PATH):
            cls._USERS.clear()
        elif os.path.getmtime(cls.FILE_PATH) > cls._LAST_UPDATE:
            cls._LAST_UPDATE = os.path.getmtime(cls.FILE_PATH)
            cls._refresh_users()

        return list(cls._USERS)

    @classmethod
    def overwrite_users(cls):
        """Overwrites the csv file with the current users set"""
        with open(cls.FILE_PATH, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerows(cls._USERS)
    
    @classmethod
    def get_user(cls, user_id:str):
        """Returns an existing user, or creates a new one if it doesn't exist"""
        users = cls.get_users()
        user = next((user for user in users if user[0] == user_id), None)
        if user: return user

        cls._USERS.add((user_id, 0))
        cls.overwrite_users()
        return (user_id, 0)
    
    @classmethod
    def pop_user(cls, user_id:str):
        """Removes a user from the users set and overwrites the csv file"""
        user = cls.get_user(user_id)
        cls._USERS.discard(user)
        cls.overwrite_users()

        return user
    
    @classmethod
    def update_credits(cls, user_id:str, credits:int):
        """Updates a user's credits and overwrites the csv file"""
        cls.pop_user(user_id)
        cls._USERS.add((user_id, credits))
        cls.overwrite_users()