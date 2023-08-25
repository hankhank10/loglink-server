import os
import glob
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, time, timedelta
import secrets
import logging
from dataclasses import dataclass

import sentry_sdk

# Import flask
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Import secrets
from . import envars

# Sentry for error logging
from sentry_sdk.integrations.flask import FlaskIntegration
# Disable this if you have self deployed and don't want to send errors to Sentry
sentry_logging = True
if sentry_logging:
    if envars.sentry_dsn:
        sentry_sdk.init(
            dsn=envars.sentry_dsn,
            integrations=[
                FlaskIntegration(),
            ],
            traces_sample_rate=1.0
        )

# Create the app
app = Flask(__name__)

# Create the DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///messages.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.json.sort_keys = False
app.config['SECRET_KEY'] = envars.app_secret_key
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Define global paths and uris
app_uri = "https://loglink.it/"
security_disclaimer_api = f"{app_uri}/security-notice/"
media_uploads_folder = "media_uploads"
beta_codes_folder = "beta_codes"
telegram_invite_link_uri = f"https://t.me/{envars.telegram_bot_name}"

latest_plugin_version = "0.0.0"
latest_plugin_version_last_checked = datetime.now()

# Global app settings
delete_immediately = True  # This setting means messages are deleted immediately after they are delivered - keep on in production, but maybe turn off for testing
token_length = 18
creating_db = False

# Image upload services
image_upload_service = "imgbb"
if image_upload_service == "imgur":
    from . import imgur
if image_upload_service == "imgbb":
    from . import imgbb

require_user_to_have_own_cloud_account = True


# Message strings
message_string = {
    "problem_creating_user_generic": "There was a problem creating your account.",
    "start_with_start_please": "Please type /start followed by your beta code to get started.",
    "beta_code_not_found": "LogLink is currently in beta and as such to sign up you must start the bot with the command /start followed by your beta code. You either didn't provide a code or it wasn't recognised.^^You can apply for a beta code at "+app_uri,
    "problem_creating_user_whitelist": "There was a problem creating your account. This may be because your mobile number is not on the whitelist.",
    "welcome_to_loglink": f"Welcome to LogLink. By continuing to use LogLink you are confirming that you have read and understood the really important security and service message here ({security_disclaimer_api}), that you accept the risks, accept that the creator(s) accept no liability and confirm that it is suitable for your use case.",
    "token_will_be_sent_in_next_message": "Your token will be sent in the next message (for easy copying). Do not share this token with anyone else.",
    "do_not_share_token": "❗Do not share your token with anyone else",
    "resetting_your_token": "Resetting your token.",
    "more_help": f"Please visit {app_uri} for more assistance",
    "error_with_message": "This message could not be saved",
    "message_type_not_supported": "This message type is not supported",
    "plugin_instructions": f"You should paste this token into your plugin settings in Logseq. See {app_uri}setup-plugin for more information.",
    "telegram_help_message": "*LogLink Help Menu*^^You can use the following commands to seek help:^^/imgbb: Connect LogLink with your imgBB account to allow image uploads^/token_refresh: Generate a new token and send it to yourself^/delete_account: Delete your account^^The full instructions are at " + app_uri + "",
    "sorry_didnt_understand_command": "Sorry, I didn't understand that command.",
    "delete_failed_not_in_database": "No record associated with this ID found in the database",
    "user_deleted": "Your account and all associated messages were deleted. If you want to use the service again, send another message.",
    "confirm_delete_account": "Are you sure you want to delete your account? This will delete all messages associated with your account.",
    "confirm_delete_account_telegram_suffix": "^^Type /delete_account_confirm to confirm.",
    "confirm_refresh_token": "Are you sure you want to refrsh your token? This will delete all messages associated with your account.",
    "confirm_refresh_token_telegram_suffix": "^^Type /token_refresh_confirm to confirm.",
    "danger_zone": "❗ DANGER ZONE ❗",
    "cannot_upload_to_cloud": "There was a problem uploading your message to the cloud. You may need to set your imgbb API key in the settings.^^Full instructions at " + app_uri + "/image-upload",
    "imgbb_no_argument": "To specify an imgbb API key, use the command /imgbb followed by your API key.^^Full instructions at " + app_uri + "image-upload",
    "imgbb_invalid_key": "I tried to send a test message to imgbb using that API key but it didn't work.^^Full instructions at " + app_uri + "image-upload",
    "imgbb_key_set": "Your imgbb API key has been set and you should now be able to upload images. Try it out!",
    "new_version_available": f"FYI, a new version of the LogLink plugin is available. Please update via the marketplace.",
    "new_version_available_desktop": f"FYI, a new version of the LogLink plugin is available for Logseq Desktop. Please update via the marketplace on your desktop.",
}

media_urls = {
    'toast': 'https://media.giphy.com/media/BPJmthQ3YRwD6QqcVD/giphy.gif',
    'sad_cat': 'https://media.giphy.com/media/71PLYtZUiPRg4/giphy.gif',
    'sad_pam': 'https://media.giphy.com/media/YLgIOmtIMUACY/giphy-downsized-large.gif'
}

# This server was originally planned to support both Telegram and Whatsapp. Telegram is required, Whatsapp is actually not implemented.
valid_providers = ['telegram']

# Telegram settings
telegram_require_beta_code = True


# Define the model in which the user data, tokens and messages are stored
@dataclass
class User(db.Model):
    id: int = db.Column(db.Integer, primary_key=True)

    token: str = db.Column(db.String(80), unique=True, nullable=False)

    provider: str = db.Column(db.String(20), nullable=False)  # eg WhatsApp

    # For whatsapp this is a phone number, for telegram this is a chat_id
    provider_id: str = db.Column(db.String(30), unique=True, nullable=True)

    approved: bool = db.Column(db.Boolean, nullable=False, default=True)

    imgbb_api_key: str = db.Column(db.String(80), nullable=True)

    api_call_count: int = db.Column(db.Integer, default=0, nullable=False)

    @property
    def messages(self):
        return Message.query.filter_by(user_id=self.id).all()


@dataclass
class Message(db.Model):
    id: int = db.Column(db.Integer, primary_key=True)

    provider: str = db.Column(db.String(20), nullable=False)  # eg WhatsApp

    provider_message_id: str = db.Column(db.String(100))

    user_id = db.Column(db.String(80), db.ForeignKey('user.id'))

    contents: str = db.Column(db.String(10000))
    timestamp: datetime = db.Column(db.DateTime)
    delivered: bool = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def minutes_old(self):
        return (datetime.now() - self.timestamp).seconds / 60


with app.app_context():
    db.create_all()

################
# HOUSEKEEPING #
################


def calculate_version_number(version):
    # This translates a github tag (eg v.1.0.7) and translates it into a integer where later versions will be higher

    version = str(version)
    version = version.replace("v", "")
    major_version = version.split(".")[0]
    minor_version = version.split(".")[1]
    patch_version = version.split(".")[2]
    version = int(major_version) * 10000 + \
        int(minor_version) * 100 + int(patch_version)
    return version


def get_latest_plugin_version():
    # Gets the latest version of the loglink pulgin from github - if you are self deploying this or using a custom plugin then you may want to change this

    url = "https://api.github.com/repos/hankhank10/loglink-plugin/releases/latest"
    logging.info("Getting latest plugin version from Github API")
    response = requests.get(url)
    if response.status_code == 200:
        response = response.json()
        version = response['tag_name']
        logging.info(f"Latest plugin version is {version}")
        return version
    else:
        logging.error(
            f"Error getting latest plugin version: {response.status_code}")
        return "0.0.0"


def list_of_beta_codes():
    # Gets the list of beta codes in the beta_codes folder
    list_of_codes = []
    for file in glob.glob(f"{beta_codes_folder}/*.txt"):
        filename = file.replace(".txt", "")
        filename = filename.replace(f"{beta_codes_folder}/", "")
        list_of_codes.append(filename)
    return list_of_codes


def use_beta_code(beta_code):
    # "Uses" a beta code by deleting it from the directory
    if beta_code in list_of_beta_codes():
        os.remove(f"{beta_codes_folder}/{beta_code}.txt")
        return True
    else:
        return False


def escape_markdown(text, carriage_return_only=False):
    if not carriage_return_only:
        char_list = [
            "_",
            "-",
            ".",
            "(",
            ")",
            "!"
        ]

        for char in char_list:
            text = text.replace(char, f"\\{char}")

    text = text.replace("^", "\n")
    return text


def delete_delivered_messages(user_id=None):
    # If user_id is provided, only delete messages for that user, otherwise delete all delivered messages for all users

    if user_id:
        messages = Message.query.filter_by(user_id=user_id, delivered=True)
    else:
        messages = Message.query.filter_by(delivered=True)

    for message in messages:
        db.session.delete(message)

    try:
        db.session.commit()
    except:
        return False
    return True


def delete_all_messages(user_id):
    # Delete all messages for a particular user

    messages = Message.query.filter_by(
        user_id=user_id
    ).delete()

    try:
        db.session.commit()
    except:
        return False
    return True


def random_token(token_type=None):
    # Generate a random token

    if token_type == "telegram":
        return "telegram"+secrets.token_hex(token_length)
    return "unknown"+secrets.token_hex(token_length)


def user_can_upload_to_cloud(user_id):
    # Check that the user both exists and has an imgbb key associated with their account

    user = User.query.filter_by(id=user_id).first()
    if not user:
        return False
    if user.imgbb_api_key:
        return True
    else:
        return False


def create_new_user(
    provider,
    provider_id,
    approved=True,
    beta_code=None
):

    if provider not in valid_providers:
        return False

    if provider == 'telegram':
        if telegram_require_beta_code:
            beta_code_ok = use_beta_code(beta_code)
            if not beta_code_ok:
                send_message(
                    provider=provider,
                    provider_id=provider_id,
                    contents=message_string["beta_code_not_found"]
                )
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

    # Get the user record
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
    try:
        db.session.add(new_message)
        db.session.commit()
    except:
        return False

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
    imgbb_api_key=None,
    caption=None
):

    # If we require the user to have their own cloud account, check whether they have one
    if require_user_to_have_own_cloud_account:
        # At the moment only imgbb is implemented
        if not imgbb_api_key:
            logging.error("No imgbb API key provided")
            return False

    # Upload the image to the cloud service
    image_upload_result = False
    if image_upload_service == "imgbb":
        image_upload_result = imgbb.upload_image(
            image_file_path,
            user_api_token=imgbb_api_key
        )
    else:
        # If image_upload_service is not set to something we recognise then return False
        return False

    if not image_upload_result:
        return False

    if image_upload_result:
        logging.info(f"Image uploaded to cloud at url {image_upload_result}")

        if caption:
            message_contents = f"{caption} ![{caption}]({image_upload_result})"
        else:
            message_contents = image_upload_result
    else:
        return False

    return message_contents


def set_user_imgbb_api_key(user_id, imgbb_api_key):

    # Check that we are even using imgbb for cloud image storage
    if image_upload_service != "imgbb":
        return False

    # Check that the user exists
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return False

    # Check the token is valid
    if not imgbb.api_key_valid(imgbb_api_key):
        return False

    # Set the user's imgbb api key
    user.imgbb_api_key = imgbb_api_key
    try:
        db.session.commit()
    except:
        return False
    return True


def send_message(
    provider,
    provider_id,
    contents,
    disable_notification=False,
):

    if provider not in valid_providers:
        return False

    if provider == 'telegram':
        telegram.send_telegram_message(
            provider_id, contents, disable_notification)
        return True

    return False


def send_picture_message(
    provider,
    provider_id,
    image_url,
    animation=False,
    caption=None,
):

    if provider not in valid_providers:
        return False

    if provider == 'telegram':
        result = telegram.send_telegram_picture_message(
            telegram_chat_id=provider_id,
            image_url=image_url,
            animation=animation,
            caption=caption
        )
        return result

    return False


def onboarding_workflow(
    provider,
    provider_id,
    beta_code=None,
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
            provider_id=provider_id,
            beta_code=beta_code
        )

    if not user:
        logging.error("Failed to create new user")
        send_message(provider, provider_id,
                     message_string["problem_creating_user_generic"])
        return False

    logging.info("New user: %s", user.provider_id)
    send_message(provider, provider_id, message_string["welcome_to_loglink"])
    send_message(provider, provider_id,
                 message_string["token_will_be_sent_in_next_message"], disable_notification=True)
    send_message(provider, provider_id, user.token, disable_notification=True)
    send_message(provider, provider_id,
                 message_string["plugin_instructions"], disable_notification=True)
    return True


def offboarding_workflow(
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
        # User is not in the database
        send_message(provider, provider_id,
                     message_string["delete_failed_not_in_database"])
        return False

    # Delete all messages associated with that user
    delete_all_messages(user.id)

    # Delete the user
    db.session.delete(user)
    db.session.commit()

    send_message(provider, provider_id, message_string["user_deleted"])
    return True


def help_send_new_token(
    user_id,
    provider,
    provider_id
):
    # Check the user is found
    user = User.query.filter_by(id=user_id).first()
    if not user:
        logging.error("User not found")
        return False

    # Delete all old messages
    delete_all_messages(user.id)

    # Refresh the token
    user.token = random_token(provider)
    db.session.commit()
    send_message(provider, provider_id, message_string["resetting_your_token"])
    send_message(provider, provider_id,
                 message_string["token_will_be_sent_in_next_message"])
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
if not creating_db:
    if 'telegram' in valid_providers:
        from . import telegram


#####################
# ROUTES            #
#####################


@app.route('/')
def index():
    return "🟢 API is running"


@app.route('/get_new_messages/', methods=['POST'])
def get_new_messages():

    # Check that we have been sent JSON
    try:
        posted_json = request.get_json()
        user_id = posted_json.get('user_id')
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

    # Get the messages from the database
    messages = Message.query.filter_by(user_id=user.id).all()

    new_messages = []
    for message in messages:
        if not message.delivered:
            message.delivered = True

            message_in_memory = message
            new_messages.append(message_in_memory)

    # Mark them as read and delete them from the database
    db.session.commit()
    if delete_immediately:
        delete_delivered_messages(user.id)

    # Version checking
    # Check whether we have already checked the latest version
    global latest_plugin_version
    if latest_plugin_version == "0.0.0" \
            or latest_plugin_version_last_checked < (datetime.now() - timedelta(hours=1)):
        latest_plugin_version = get_latest_plugin_version()

    # Check if a version number was sent
    plugin_version = posted_json.get('plugin_version')
    logging.info(
        f"User version is {plugin_version}, latest found on github is {latest_plugin_version}")
    if plugin_version:
        print("Plugin version: " + plugin_version +
              " vs latest " + latest_plugin_version)
        cumulative_plugin_version = calculate_version_number(plugin_version)
        cumulative_latest_plugin_version = calculate_version_number(
            latest_plugin_version)
        try:
            if cumulative_plugin_version < cumulative_latest_plugin_version:
                logging.info('Old version detected: ' + str(cumulative_plugin_version) +
                             ' < ' + str(cumulative_latest_plugin_version))
                new_messages.append({
                    'contents': message_string['new_version_available'],
                })
                send_message(
                    user.provider,
                    user.provider_id,
                    message_string['new_version_available_desktop'],
                    True
                )
        except:
            logging.error('Error comparing version numbers')

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


#########
# ADMIN #
#########

def send_service_message(
    contents,
    user_id=None
):
    # Send a service message to a particular user, or if a user_id is not provided, to all users

    telegram_provider_id_list_to_send_message_to = []

    if user_id:
        user = User.query.filter_by(id=user_id).first()
        if user:
            if user.provider == "telegram":
                telegram_provider_id_list_to_send_message_to.append(
                    user.provider_id)

    else:
        telegram_provider_id_list_to_send_message_to = [
            user.provider_id for user in User.query.filter_by(provider="telegram").all()]

    for telegram_provider_id in telegram_provider_id_list_to_send_message_to:
        telegram.send_telegram_message(
            telegram_provider_id,
            contents,
            disable_notification=True
        )


def check_db():
    return {
        'users': User.query.count(),
        'messages': {
            'total': Message.query.count(),
            'delivered': Message.query.filter_by(delivered=True).count(),
            'undelivered': Message.query.filter_by(delivered=False).count()
        }
    }


def is_admin_password_valid(
    password_provided
):
    if password_provided == envars.admin_password:
        return True
    else:
        return False


invalid_admin_password_message = {
    "status": "error",
    "message": "Invalid admin password"
}


@app.route('/admin')
def admin_home():
    admin_password_provided = request.headers.get('admin-password')
    if not is_admin_password_valid(admin_password_provided):
        return invalid_admin_password_message, 401

    return "🟢 Admin API is running"


@app.route('/admin/health')
def check_health():

    admin_password_provided = request.headers.get('admin-password')
    if not is_admin_password_valid(admin_password_provided):
        return invalid_admin_password_message, 401

    telegram_health = telegram.check_webhook_health()

    return {
        'server': {
            'ok': True
        },
        'database': check_db(),
        'telegram_webhook': telegram.check_webhook_health()
    }


@app.route('/admin/beta_codes', methods=['GET', 'POST'])
def beta_codes_route():

    admin_password_provided = request.headers.get('admin-password')
    if not is_admin_password_valid(admin_password_provided):
        return invalid_admin_password_message, 401

    if request.method == 'POST':
        # This creates a new beta code

        # Check that we have been sent JSON
        telegram_beta_link_uri = f"{telegram_invite_link_uri}?start="

        # Get the number of codes and check it's an integer
        number_of_codes = request.json.get('number_of_codes')
        if not number_of_codes:
            return {
                "status": "error",
                "message": "No number_of_codes provided"
            }, 400

        # Check that number of codes is an integer
        try:
            number_of_codes = int(number_of_codes)
        except:
            return {
                "status": "error",
                "message": "number_of_codes must be an integer"
            }, 400

        # Create the codes
        list_of_codes = []
        for i in range(number_of_codes):
            new_code = secrets.token_hex(5)
            open(f"{beta_codes_folder}/{new_code}.txt", "w").close()
            list_of_codes.append(new_code)

        return {
            "status": "success",
            "codes_added": list_of_codes
        }

    if request.method == 'GET':
        result = list_of_beta_codes()
        return {
            'status': 'success',
            'count': len(result),
            'codes': result
        }
