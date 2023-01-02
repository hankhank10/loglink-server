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

# Define global paths and uris
app_uri = "https://loglink.it/"
media_uploads_folder = "media_uploads"

# Global app settings
whitelist_only = True
delete_immediately = True  # This setting means messages are deleted immediately after they are delivered - keep on in production, but maybe turn off for testing
token_length = 18

# Message strings
message_string = {
    "problem_creating_user_generic": "There was a problem creating your account.",
    "problem_creating_user_whitelist": "There was a problem creating your account. This may be because your mobile number is not on the whitelist.",
    "welcome_to_loglink": "Welcome to LogLink, your token will be sent in the next message (for easy copying)",
    "token_will_be_sent_in_next_message": "Your token will be sent in the next message (for easy copying)",
    "resetting_your_token": "Resetting your token.",
    "token_reset": "Your refreshed token will be sent in the next message (for easy copying). You will need to re-input this into your plugin settings.",
    "more_help": f"Please visit {app_uri} for more assistance",
    "error_with_message": "This message could not be saved",
    "plugin_instructions": "You should paste this token into your plugin settings in LogSeq",
}

# Valid providers
valid_providers = [
    "whatsapp",
    "telegram",
]


# Define the model in which the user data, tokens and messages are stored
@dataclass
class User(db.Model):
    id:int = db.Column(db.Integer, primary_key=True)

    token:str = db.Column(db.String(80), unique=True, nullable=False)
    provider_id:str = db.Column(db.String(30), unique=True, nullable=True)  # For whatsapp this is a phone number, for telegram this is a chat_id

    provider:str = db.Column(db.String(20), nullable=False)  # eg WhatsApp
    approved:bool = db.Column(db.Boolean, nullable=False, default=True)

    api_call_count:int = db.Column(db.Integer, default=0)


@dataclass
class Message(db.Model):
    id:int = db.Column(db.Integer, primary_key=True)

    provider:str = db.Column(db.String(20), nullable=False)  # eg WhatsApp

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


def random_token(token_type=None):
    if token_type == "whatsapp":
        return "whatsapp"+secrets.token_hex(token_length)
    if token_type == "telegram":
        return "telegram"+secrets.token_hex(token_length)
    return "unknown"+secrets.token_hex(token_length)


def create_new_user(
    provider,
    provider_id,
    approved=True
):

    if provider not in valid_providers:
        return False

    # If whitelist only, check if the phone number is in the whitelist
    if whitelist_only:
        if provider == "whatsapp":
            if provider_id not in whitelist.acceptable_numbers:
                return False

    new_user = User(
        provider_id=provider_id,
        token=random_token(provider),
        provider=provider,
        approved=approved
    )
    db.session.add(new_user)
    db.session.commit()
    return new_user


def add_new_message(
    user_id,
    provider,
    message_contents,
    provider_message_id=None,
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
        provider_message_id=provider_message_id,
        provider=provider,
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
        image_file_path,
        caption=None
):

    # Upload the image to imgur
    imgur_result = imgur.upload_image(image_file_path)

    if not imgur_result:
        return False

    if imgur_result:
        logging.info(f"Image uploaded to imgur at url {imgur_result}")

        if caption:
            message_contents = f"{caption} ![{caption}]({imgur_result})"
        else:
            message_contents = imgur_result

    return message_contents


def send_message(
    provider,
    provider_id,
    contents
):

    if provider not in valid_providers:
        return False

    if provider == 'whatsapp':
        whatsapp.whatsapp_messenger.send_message(contents, provider_id)
        return True

    if provider == 'telegram':
        telegram.send_telegram_message(provider_id, contents)
        return True

    return False


def onboarding_workflow(
    provider,
    provider_id
):

    if provider not in valid_providers:
        return False

    # Check if this provider ID is already in the database
    user = User.query.filter_by(
        provider=provider,
        provider_id=provider_id
    ).first()

    if not user:
        # Create a new user
        user = create_new_user(
            provider=provider,
            provider_id=provider_id
        )

    if not user:
        logging.error("Failed to create new user")
        if whitelist_only:
            send_message(provider, provider_id, message_string["problem_creating_user"])
        else:
            send_message(provider, provider_id, message_string["problem_creating_user_generic"])
        return False

    logging.info("New user: %s", user.provider_id)
    send_message(provider, provider_id, message_string["welcome_to_loglink"])
    send_message(provider, provider_id, user.token)
    send_message(provider, provider_id, message_string["plugin_instructions"])
    return True


def help_send_token_reminder(
    user_id,
    provider,
    provider_id
):
    user = User.query.filter_by(id=user_id).first()
    if not user:
        logging.error("User not found")
        return False
    send_message(provider, provider_id, message_string["token_will_be_sent_in_next_message"])
    send_message(provider, provider_id, user.token)
    return True


def help_send_new_token(
    user_id,
    provider,
    provider_id
):
    user = User.query.filter_by(id=user_id).first()
    if not user:
        logging.error("User not found")
        return False
    user.token = random_token(provider)
    db.session.commit()
    send_message(provider, provider_id, message_string["resetting_your_token"])
    send_message(provider, provider_id, message_string["token_reset"])
    send_message(provider, provider_id, user.token)
    return True


def help_more_help(
    user_id,
    provider,
    provider_id
):
    send_message(provider, provider_id, message_string["more_help"])
    return True


# Import other routes
import whatsapp
import telegram


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
            if message.provider == "whatsapp":
                whatsapp.mark_whatsapp_message_read(message.provider_message_id)

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
