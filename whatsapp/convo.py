from wapp_agent import WAppAgent
from datetime import datetime
import requests
from flask import Flask, jsonify, request
from queue import Queue, Empty
import asyncio

class Convo:
    def __init__(self, agent, user_id):
        self.agent = agent
        self.user_id = user_id
        self.user_name = None
    
    async def send_message(self, content):
        user = self.user_id
        if user == '5218114142626':
            user = '528114142626'
        await self.agent.send_message(user, content)
    
    async def wait_for_message(self):
        msg = await self.agent.wait_for_message(self.user_id)
        msg = ConvoMessage(msg)
        return msg

    async def prompt(self, prompt):
        await self.send_message(prompt)
        return await self.wait_for_message()

    @staticmethod
    async def setup_agent(agent, handler):
        convos = set()
        def conversation_done(convo):
            print(f"Conversation with {convo.user_id} done.")
            convos.remove(convo)
            del convo.agent.messages[convo.user_id]

        agent.start_listening()
        while True:
            for sender in list(agent.messages.keys()):
                if not any(convo.user_id == sender for convo in convos):
                    convo = Convo(agent, sender)
                    convos.add(convo)
                    task = asyncio.create_task(handler(convo))
                    task.add_done_callback(lambda t: conversation_done(convo))

            await asyncio.sleep(1)

class ConvoMessage:
    def __init__(self, msg_dict):
        self.msg = msg_dict
    
    @property
    def timestamp(self):
        return int(self.msg.get('timestamp', 0))

    @property
    def text(self):
        text = (self.msg.get('text', {}).get('body')
                or self.msg.get('interactive', {}).get('list_reply', {}).get('title')
                or self.msg.get('interactive', {}).get('button_reply', {}).get('title'))
        return text