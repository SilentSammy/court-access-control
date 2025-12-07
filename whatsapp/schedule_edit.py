import json
import traceback
import os
import wapp_agent
from wapp_agent import WAppAgent
from convo import Convo
import asyncio
from datetime import datetime, timezone, timedelta
from session import Session, Timestamp
from schedule import Schedule, ScheduleDisplayer, ScheduleItem
from user import User, UserManager
from smart_scheduler import SmartScheduler

cost_per_minute = 1

class ScheduleEdit:
    """Represents a schedule edit operation"""
    def __init__(self, user, sessions_to_add=None, sessions_to_cancel=None):
        self.sessions_to_add = sessions_to_add or []
        self.sessions_to_cancel = sessions_to_cancel or []
        self.user = user
    
    @property
    def all_sessions(self):
        return self.sessions_to_add + self.sessions_to_cancel

    @property
    def cost_to_add(self):
        return sum(session.span for session in self.sessions_to_add) * cost_per_minute
    
    @property
    def cancellation_refund(self):
        return sum(session.span for session in self.sessions_to_cancel) * cost_per_minute
    
    @property
    def net_cost(self):
        return self.cost_to_add - self.cancellation_refund

    def get_session_cost(self, session):
        return session.span * cost_per_minute

    def filter_past_deadline(self):
        """Filter out the sessions that are past their cancellation deadline"""

        # we copy the list to compare the changes
        filtered_sessions = list(self.sessions_to_cancel)

        # we filter out the sessions that are past their cancellation deadline
        self.sessions_to_cancel = [session for session in self.sessions_to_cancel if not ScheduleItem.from_session(session, self.user.id).past_deadline()]

        # we filter out the sessions that were removed
        filtered_sessions = [session for session in filtered_sessions if session not in self.sessions_to_cancel]
        return filtered_sessions
    
    def filter_ended(self):
        """Filter out the sessions that have ended"""

        # we copy the list to compare the changes
        filtered_sessions = list(self.sessions_to_add)

        # we filter out the sessions that have ended
        self.sessions_to_add = [session for session in self.sessions_to_add if not session.has_ended()]

        # we obtain the sessions that were filtered out
        filtered_sessions = [session for session in filtered_sessions if session not in self.sessions_to_add]
        return filtered_sessions

    def filter_conflicting(self):
        """Filter out the sessions that conflict with other sessions in the sessions_to_add list, or with the existing schedule"""

        # we copy the list to compare the changes
        filtered_sessions = list(self.sessions_to_add)
        
        # remove sessions that conflict with other sessions in the sessions_to_add list, but keep the first one
        temp_sessions = list(self.sessions_to_add) # create a copy of the list
        self.sessions_to_add = [] # clear the list
        while temp_sessions:
            session = temp_sessions.pop(0) # get the first session
            # add the session back to the list
            self.sessions_to_add.append(session)

            # get the sessions that conflict with the current session
            conflicting_sessions = [sess for sess in temp_sessions if sess.conflicts_with(session)]
            # remove the conflicting sessions
            temp_sessions = [sess for sess in temp_sessions if sess not in conflicting_sessions]
        
        # remove sessions that conflict with the existing schedule
        for room in set(session.room for session in self.sessions_to_add):
            # get the existing schedule for the room
            schedule = [si.session for si in Schedule(room).schedule]
            schedule = [sess for sess in schedule if sess not in self.sessions_to_cancel]
            # remove sessions that conflict with the existing schedule
            self.sessions_to_add = [session for session in self.sessions_to_add if not any(session.conflicts_with(existing_session) for existing_session in schedule)]
        
        # we obtain the sessions that were removed
        filtered_sessions = [session for session in filtered_sessions if session not in self.sessions_to_add]
        return filtered_sessions
    
    def filter_unaffordable(self):
        """Filter out the sessions that the user wouldn't be able to afford"""

        # we copy the list to compare the changes
        filtered_sessions = list(self.sessions_to_add)

        # remove sessions that the user wouldn't be able to afford
        cost_to_add = self.cost_to_add
        cost_to_cancel = self.cancellation_refund
        user_credits = self.user.credits + cost_to_cancel # calculate the user's credits after the refunds
        affordable_sessions = []
        for session in self.sessions_to_add:
            session_cost = session.span * cost_per_minute
            if user_credits >= session_cost:
                user_credits -= session_cost
                affordable_sessions.append(session)
        self.sessions_to_add = affordable_sessions

        # we obtain the sessions that were filtered out
        filtered_sessions = [session for session in filtered_sessions if session not in self.sessions_to_add]
        return filtered_sessions
    
    def apply_all_filters(self):
        """Apply all the filters to the sessions"""
        self.filter_past_deadline()
        self.filter_ended()
        self.filter_conflicting()
        self.filter_unaffordable()

    def group_by_room(self):
        """Group the sessions to add by room"""
        sessions_by_room = {}
        for session in self.all_sessions:
            sessions_by_room.setdefault(session.room, {"add": [], "cancel": []})
            if session in self.sessions_to_add:
                sessions_by_room[session.room]["add"].append(session)
            else:
                sessions_by_room[session.room]["cancel"].append(session)
        return sessions_by_room
    
    def book_sessions(self):
        """Save the sessions to the database, and deduct the cost from the user's credits"""
        booked = []

        for s in self.sessions_to_add:
            # check if user can afford the session
            if self.user.credits < s.span * cost_per_minute:
                continue

            # attempt to add the session to the schedule
            added = Schedule(s.room).add_session(s, self.user.id)
            if added:
                cost = self.get_session_cost(s)
                self.user.credits -= cost # deduct the cost from the user's credits
                booked.append(s) # add the session to the list of booked sessions
        return booked
    
    def cancel_sessions(self):
        """Refund the sessions to the user's credits"""
        user = self.user
        cancelled = []
        for sess in self.sessions_to_cancel:
            removed = Schedule.delete_session(sess)
            if removed:
                cost = self.get_session_cost(sess)
                user.credits += cost
                cancelled.append(sess)
        return cancelled
