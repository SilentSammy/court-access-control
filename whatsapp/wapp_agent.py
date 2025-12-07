import os
from datetime import datetime
import requests
from flask import Flask, jsonify, request
from queue import Queue, Empty
import asyncio
import aiohttp
from datetime import datetime
from aiohttp import FormData
import json

class WAppAgent:
    """This class can receive and send Whatsapp messages."""
    def __init__(self, url, token, challenge, phone):
        self.url = url
        self.phone = phone
        self.token = token
        self.challenge = challenge
        self.webserver = Flask(__name__)
        self.webserver.before_request(self._handle_request)
        self.messages = {}  # Add a dict of queues to store messages

    @property
    def messages_url(self):
        """The URL to send messages to"""
        return f"{self.url}/{self.phone}/messages"
    
    @property
    def media_url(self):
        """The URL to send media to"""
        return f"{self.url}/{self.phone}/media"
    
    @property
    def auth_header(self):
        """The auth header to be used in the requests"""
        return {"Authorization": f"Bearer {self.token}"}
    
    def start_listening(self):
        # Start the Flask app in a separate thread
        from threading import Thread
        flask_thread = Thread(target=self.webserver.run)
        flask_thread.start()

    def _handle_request(self):
        # if meta makes a token verification request return the agreed upon challenge token
        if request.method == "GET":
            return request.args.get('hub.challenge') if request.args.get('hub.verify_token') == self.challenge else "AuthError"

        # if it's a message put it in its respective queue
        data = request.get_json()
        if 'messages' in data['entry'][0]['changes'][0]['value']:
            message = data['entry'][0]['changes'][0]['value']['messages'][0]
            print(f"Received message [{datetime.now()}]\n{message}")
            self.messages.setdefault(message['from'], Queue()).put(message)

        return jsonify({"status": "success"}, 200)
    
    async def wait_for_message(self, recipient_id):
        """Asynchronously wait for the next message."""
        while True:
            try:
                return self.messages.setdefault(recipient_id, Queue()).get_nowait()  # Try to get message without blocking
            except Empty:
                await asyncio.sleep(0.1) 

    async def send_message(self, to, content):
        # Assemble the message JSON body
        message = build_base_message(to)
        if not isinstance(content, dict):
            content = build_text(str(content))
        message = {**message, **content}

        # Send it via an HTTP POST request to the Whatsapp API
        print(f"Sending message [{datetime.now()}]\n{message}")
        result = await post_with_auth(self.messages_url, message, self.auth_header)
        return result

    async def upload_media(self, media_path):
        data = aiohttp.FormData()
        data.add_field('messaging_product', 'whatsapp')
        data.add_field('type', 'image/png')
        data.add_field('file', open(media_path, 'rb'), filename=media_path, content_type='image/png')

        async with aiohttp.ClientSession() as session:
            async with session.post(self.media_url, headers=self.auth_header, data=data) as response:
                response_json = await response.json()
                return response_json['id']


async def post_with_auth(url, json_data, auth_header):
    response = None
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=json_data, headers=auth_header) as response:
            print(f"Message sent [{datetime.now()}]: {response.status} {response.text if response.status != 200 else ''}")
    await asyncio.sleep(0.01) # small delay
    return response

def build_base_message(to=None):
    msg = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual"
    }
    if to:
        msg["to"] = to
    return msg

def build_text(body=""):
    return {
        "type": "text",
        "text": {
            "body": body
        }
    }

def build_media(media_id, type="image"):
    return {
        'type': type,
        type: {
            'id': media_id
        }
    }

def build_interactive(body="", header=None, footer=None, interactive=None):
    # header, body and footer are optional strings
    interactive = {} if interactive is None else interactive
    if header:
        interactive["header"] = { "type": "text", "text": header }
    if body:
        interactive["body"] = { "text": body }
    if footer:
        interactive["footer"] = { "text": footer }
    return {
        "type": "interactive",
        "interactive": interactive
    }

def create_interactive_list(button, rows: list):
    # rows will be a list of strings, we need to convert it to a list of objects
    rows = [{"id": f"row_{i}", "title": row} for i, row in enumerate(rows)]
    return {
        "type": "list",
        "action": {
            "button": button,
            "sections": [ { "rows": rows } ]
        }
    }

def create_interactive_buttons(buttons: list):
    buttons = [{"type": "reply", "reply": {"id": f"button_{i}", "title": button}} for i, button in enumerate(buttons)]
    return {
        "type": "button",
        "action": {
            "buttons": buttons
        }
    }

async def main():
    # Create a WAppAgent object
    agent = WAppAgent(
        "https://graph.facebook.com/v18.0",
        open(os.path.dirname(os.path.abspath(__file__))+'\\token.txt', 'r').read(),
        "12345678",
        "109825938838824"
    )

    # agent.upload_media("whatsapp/output.png")
    # await agent.send_message('50766180742', 'hello world')
    # media_id = await agent.upload_media("whatsapp/schedule/output.png")
    # await agent.send_message('50766180742', build_media(media_id))

if __name__ == "__main__":
    asyncio.run(main())
