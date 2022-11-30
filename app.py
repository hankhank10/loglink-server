import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, time, timedelta
import secrets
import logging
from dataclasses import dataclass

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


# Define the model in which the user data, tokens and messages are stored
@dataclass
class User(db.Model):
    id:int = db.Column(db.Integer, primary_key=True)

    token = db.Column(db.String(80), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)

    api_call_count:int = db.Column(db.Integer, default=0)


@dataclass
class Message(db.Model):
    id:int = db.Column(db.Integer, primary_key=True)

    whatsapp_message_id:str = db.Column(db.String(100), nullable=False)

    user_id = db.Column(db.String(80), db.ForeignKey('user.id'))

    contents:str = db.Column(db.String(5000))
    timestamp:datetime = db.Column(db.DateTime)
    delivered:bool = db.Column(db.Boolean, default=False)

    @property
    def minutes_old(self):
        return (datetime.now() - self.timestamp).seconds / 60



# Define global paths and uris
app_uri = "https://whatsapp.logspot.top/"



#################
# HOUSEKEEPING #
#################


def delete_delivered_messages(user_id):
    messages = Message.query.filter_by(user_id=user_id, delivered=True)
    for message in messages:
        db.session.delete(message)
    db.session.commit()




#####################
# WHATSAPP API CALLS #
#####################





#####################
# ROUTES            #
#####################


@app.route('/')
def index():
    return "Hello world"


@app.route('/webhook', methods=['GET', 'POST'])
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
                    user = User(phone_number=mobile, token="whatsapp"+secrets.token_hex(4))
                    db.session.add(user)
                    db.session.commit()
                    logging.info("New user: %s", mobile)
                    messenger.send_message("Welcome to LogText, your token will be send in the next message", mobile)
                    messenger.send_message(user.token, mobile)
                    return "ok"

                # If it is an existing user, add the message to the database
                if user:

                    message_id = messenger.get_message_id(data)

                    user.api_call_count = user.api_call_count + 1
                    db.session.commit()

                    #logging.info("User: %s, API calls: %s", mobile, user.api_call_count)

                    new_message = Message(
                        user_id=user.id,
                        whatsapp_message_id=message_id,
                        contents=messenger.get_message(data),
                        timestamp=datetime.now(),
                    )
                    db.session.add(new_message)
                    db.session.commit()
                    #logging.info("New message: %s", new_message.contents)

                    #messenger.send_message(new_message.contents, mobile)

                    return "ok"

    return "ok"


@app.route('/get_new_messages/<token>/', methods=['GET'])
def get_new_messages(token):
    user = User.query.filter_by(token=token).first()

    if not user:
        return jsonify({"error": "Invalid token"}), 401

    messages = Message.query.filter_by(user_id=user.id).all()

    new_messages = []
    for message in messages:
        if not message.delivered:
            message.delivered = True
            new_messages.append(message)

    db.session.commit()

    if new_messages:
        if len(new_messages) == 1:
            response = "1 new message downloaded by LogSeq"
        else:
            response = f"{len(new_messages)} new messages downloaded by LogSeq"
        messenger.send_message(response, user.phone_number)

    delete_delivered_messages(user.id)

    return jsonify({
        'status': 'success',
        'user': {
            'token': user.token,
            'api_call_count': user.api_call_count,
        },
        'messages': {
            'count': len(new_messages),
            'contents': new_messages
        }
    }), 200


# Run the app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)
