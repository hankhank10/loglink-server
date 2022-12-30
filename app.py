import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, time, timedelta
import secrets
import logging
from dataclasses import dataclass
import imgur

# Import flask
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Import secrets
import secretstuff
import whitelist

# Create the app
app = Flask(__name__)

# Create the DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///messages.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config["JSON_SORT_KEYS"] = False
app.config['SECRET_KEY'] = secretstuff.app_secret_key
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Set up Heyoo for WhatsApp API
from heyoo import WhatsApp
whatsapp_messenger = WhatsApp(
    token=secretstuff.whatsapp_token,
    phone_number_id=secretstuff.whatsapp_phone_number_id
)

# Whatsapp APIs addresses for calls outside Heyoo (at the moment only setting read receipts)
whatsapp_api_base_uri = "https://graph.facebook.com/v15.0/"
whatsapp_api_messages_uri = whatsapp_api_base_uri + secretstuff.whatsapp_phone_number_id + "/messages"

# Define global paths and uris
app_uri = "https://loglink.it/"

# Global app settings
whitelist_only = True
delete_immediately = True  # This setting means messages are deleted immediately after they are delivered - keep on in production, but maybe turn off for testing

# Message strings
message_string = {
    "problem_creating_user_generic": "There was a problem creating your account.",
    "problem_creating_user_whitelist": "There was a problem creating your account. This may be because your mobile number is not on the whitelist.",
    "welcome_to_loglink": "Welcome to LogLink, your token will be send in the next message (for easy copying)",
    "token_will_be_sent_in_next_message": "Your token will be sent in the next message (for easy copying)",
    "resetting_your_token": "Resetting your token.",
    "token_reset": "Your refreshed token will be sent in the next message (for easy copying). You will need to re-input this into your plugin settings.",
    "more_help": f"Please visit {app_uri} for more assistance"
}


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

    provider_message_id:str = db.Column(db.String(100))

    user_id = db.Column(db.String(80), db.ForeignKey('user.id'))

    contents:str = db.Column(db.String(10000))
    timestamp:datetime = db.Column(db.DateTime)
    delivered:bool = db.Column(db.Boolean, default=False)

    @property
    def minutes_old(self):
        return (datetime.now() - self.timestamp).seconds / 60


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
    # If whitelist only, check if the phone number is in the whitelist
    if whitelist_only:
        if phone_number not in whitelist.acceptable_numbers:
            return False

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


def add_new_message(
    user_id,
    received_from,
    message_contents,
    whatsapp_message_id=None,
):

    # Get the user
    user = User.query.filter_by(id=user_id).first()

    if not user:
        return False

    # Add to the user's API count
    user.api_call_count = user.api_call_count + 1
    db.session.commit()

    # Create the message
    new_message = Message(
        user_id=user_id,
        provider_message_id=whatsapp_message_id,
        received_from=received_from,
        contents=message_contents,
        timestamp=datetime.now(),
    )
    db.session.add(new_message)
    db.session.commit()

    return True


def compose_location_message_contents(
        location_latitude,
        location_longitude,
        location_name=None,
        location_address=None,
        location_url=None,
):

    message_contents = None

    location_pin = "📍"
    location_details = ""

    if location_name:
        location_details = location_name

    if location_address:
        if location_details:
            location_details = f"{location_details}, "
        location_details = f"{location_details}{location_address}"
    else:
        if location_details:
            location_details = f"{location_details} {location_latitude}, {location_longitude})"
        else:
            location_details = f"Lat: {location_latitude}, Lon: {location_longitude}"

    if location_url:
        location_details = f"{location_details} {location_url}"

    google_maps_base_url = "https://maps.google.com/maps?q="
    google_maps_address = f"{google_maps_base_url}{location_latitude},{location_longitude}"

    message_contents = f"{location_pin} {location_details} {google_maps_address}"

    return message_contents


def compose_image_message_contents(
        image_filename,
        caption=None
):

    # Upload the image to imgur
    imgur_result = imgur.upload_image(image_filename)

    if not imgur_result:
        return False

    if imgur_result:
        logging.info(f"Image uploaded to imgur at url {imgur_result}")

        if caption:
            message_contents = f"{caption} ![{caption}]({imgur_result})"
        else:
            message_contents = imgur_result

    return message_contents


# Import other routes
import whatsapp

#####################
# ROUTES            #
#####################

@app.route('/')
def index():
    return "API is running"


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
                mark_whatsapp_message_read(message.provider_message_id)

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


#####################
# TELEGRAM          #
#####################

# Run the app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5010, debug=True)
