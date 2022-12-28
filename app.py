import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, time, timedelta
import secrets
import logging
from dataclasses import dataclass

from cryptography.fernet import Fernet

# Import flask
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Import secrets
import secretstuff

# Create the app
app = Flask(__name__)

# Create the DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///whatsapp.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config["JSON_SORT_KEYS"] = False
app.config['SECRET_KEY'] = secretstuff.app_secret_key
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Set up Heyoo
from heyoo import WhatsApp
messenger = WhatsApp(
    token=secretstuff.whatsapp_token,
    phone_number_id=secretstuff.whatsapp_phone_number_id
)

# Whatsapp APIs addresses for calls outside Heyoo
whatsapp_api_base_uri = "https://graph.facebook.com/v15.0/"
whatsapp_api_messages_uri = whatsapp_api_base_uri + secretstuff.whatsapp_phone_number_id + "/messages"


# Define the model in which the user data, tokens and messages are stored
@dataclass
class User(db.Model):
    id:int = db.Column(db.Integer, primary_key=True)

    token:str = db.Column(db.String(80), unique=True, nullable=False)
    phone_number:str = db.Column(db.String(20), unique=True, nullable=True)

    account_type:str = db.Column(db.String(20), nullable=False)  # eg WhatsApp
    approved:bool = db.Column(db.Boolean, nullable=False, default=True)

    api_call_count:int = db.Column(db.Integer, default=0)


@dataclass
class Message(db.Model):
    id:int = db.Column(db.Integer, primary_key=True)

    received_from:str = db.Column(db.String(20), nullable=False)  # eg WhatsApp

    whatsapp_message_id:str = db.Column(db.String(100))

    user_id = db.Column(db.String(80), db.ForeignKey('user.id'))

    contents:str = db.Column(db.String(10000))
    timestamp:datetime = db.Column(db.DateTime)
    delivered:bool = db.Column(db.Boolean, default=False)

    @property
    def minutes_old(self):
        return (datetime.now() - self.timestamp).seconds / 60



# Define global paths and uris
app_uri = "https://loglink.it/"

# App settings
delete_immediately = True  # This setting means messages are deleted immediately after they are delivered - keep on in production, but maybe turn off for testing


#################
# HOUSEKEEPING #
#################


def delete_delivered_messages(user_id):
    messages = Message.query.filter_by(user_id=user_id, delivered=True)
    for message in messages:
        db.session.delete(message)
    db.session.commit()


def mark_whatsapp_message_read(message_id):
    r = requests.post(
        url = whatsapp_api_messages_uri,
        headers = {"Authorization": "Bearer " + secretstuff.whatsapp_token},
        json = {
            "messaging_product": "whatsapp",
            "message_id": message_id,
            "status": "read"
        }
    )
    return r


def random_token(token_type="whatsapp"):
    length = 4
    if token_type == "whatsapp":
        return "whatsapp"+secrets.token_hex(length)
    return "unknown"+secrets.token_hex(length)


def create_new_user(
    account_type="whatsapp",
    approved=True,
    phone_number=None
):

    if account_type.lower() == "whatsapp":
        new_user = User(
            phone_number=phone_number,
            token=random_token(),
            account_type="whatsapp",
            approved=approved
        )
        db.session.add(new_user)
        db.session.commit()
        return new_user

    return False


#####################
# ROUTES            #
#####################


@app.route('/')
def index():
    return "API is running"

#####################
# WHATSAPP          #
#####################

@app.route('/whatsapp/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == secretstuff.verify_token:
            logging.info("Verified webhook")
            response = make_response(request.args.get("hub.challenge"), 200)
            response.mimetype = "text/plain"
            return response
        logging.error("Webhook Verification failed")
        return "Invalid verification token"

    data = request.get_json()
    # logging.info("Received webhook data: %s", data)

    changed_field = messenger.changed_field(data)
    if changed_field == "messages":
        new_message = messenger.get_mobile(data)
        if new_message:

            # Get all the details of the sender
            mobile = messenger.get_mobile(data)
            name = messenger.get_name(data)
            message_type = messenger.get_message_type(data)

            logging.info(
                f"New Message; sender:{mobile} name:{name} type:{message_type}"
            )
            if message_type == "text":
                # Check if this is a new user
                user = User.query.filter_by(phone_number=mobile).first()

                # If it is a new user, create the account and return the token
                if not user:
                    user = create_new_user(
                        account_type="whatsapp",
                        phone_number = mobile
                    )
                    if not user:
                        logging.error("Failed to create new user")
                        return "Failed to create new user"

                    logging.info("New user: %s", user.phone_number)
                    messenger.send_message("Welcome to LogLink, your token will be send in the next message", mobile)
                    messenger.send_message(user.token, mobile)
                    return "ok"

                # If it is an existing user, add the message to the database
                if user:
                    message_contents = messenger.get_message(data)

                    # Check whether the message contains a command
                    command_list = [
                        "help",
                        "token",
                        "refresh"
                    ]

                    if message_contents.lower() == "help":
                        messenger.send_reply_button(
                            recipient_id=mobile,
                            button={
                                "type": "button",
                                "header": "LogLink Help",
                                "body": {
                                    "text": "How can I help you?"
                                },
                                "action": {
                                    "buttons": [
                                        {
                                            "type": "reply",
                                            "reply": {
                                                "id": "token_reminder",
                                                "title": "Send token reminder"
                                            }
                                        },
                                        {
                                            "type": "reply",
                                            "reply": {
                                                "id": "new_token",
                                                "title": "Request a new token"
                                            }
                                        },
                                        {
                                            "type": "reply",
                                            "reply": {
                                                "id": "more_help",
                                                "title": "I need more help"
                                            }
                                        }
                                    ]
                                }
                            },
                        )

                    if message_contents.lower() == "token":
                        messenger.send_message("Your token will be sent in the next message", mobile)
                        messenger.send_message(user.token, mobile)
                        messenger.send_message("If you want to refresh your token, please send the word REFRESH to receive a new token", mobile)

                    if message_contents.lower() == "refresh":
                        user.token = random_token()
                        db.session.commit()
                        messenger.send_message("Your refreshed token will be sent in the next message", mobile)
                        messenger.send_message(user.token, mobile)

                    # If the message contains a command only, exit the function so it is not added to the database
                    if message_contents.lower() in command_list:
                        return "ok"

                    message_id = messenger.get_message_id(data)

                    user.api_call_count = user.api_call_count + 1
                    db.session.commit()

                    new_message = Message(
                        user_id=user.id,
                        whatsapp_message_id=message_id,
                        received_from="whatsapp",
                        contents=message_contents,
                        timestamp=datetime.now(),
                    )
                    db.session.add(new_message)
                    db.session.commit()

                    return "ok"

    return "ok"


#####################
# OUTPUT            #
#####################

@app.route('/get_new_messages/', methods=['POST'])
def get_new_messages():

    # Check that we have been sent JSON
    try:
        posted_json = request.get_json()
        user_id = posted_json['user_id']
    except:
        return jsonify({
            'status': 'error',
            'error_type': 'failure_parsing_json',
            'message': 'Failure parsing JSON or no JSON received',
        }), 400

    # Check that the user_id was provided
    if not user_id:
        return {
            'status': 'error',
            'error_type': 'no_user_id',
            'message': 'No user_id provided in JSON'
        }, 400

    # Get the user record
    user = User.query.filter_by(token=user_id).first()

    if not user:
        return {
            'status': 'error',
            'error_type': 'user_not_found',
            'message': 'No user found with that token. Try refreshing your token at ' + app_uri + ' and is ensure it is correctly entered in settings.'
        }, 404

    # Get the messages
    messages = Message.query.filter_by(user_id=user.id).all()

    new_messages = []
    for message in messages:
        if not message.delivered:
            message.delivered = True

            message_in_memory = message
            new_messages.append(message_in_memory)
            if message.received_from == "whatsapp":
                mark_whatsapp_message_read(message.whatsapp_message_id)

    # Mark them as read and delete them from the database
    db.session.commit()
    if delete_immediately:
        delete_delivered_messages(user.id)

    return jsonify({
        'status': 'success',
        'user': {
            'token': user.token,
            'api_call_count': user.api_call_count,
            'approved': user.approved,
        },
        'messages': {
            'count': len(new_messages),
            'contents': new_messages
        }
    }), 200


# Run the app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5010, debug=True)
