import logging
import secrets
import requests
import pprint  # for debug
from flask import Flask, request

from . import app
from . import add_new_message, compose_location_message_contents, compose_image_message_contents

from . import db
from . import User

from . import message_string, media_uploads_folder

from . import send_message, send_picture_message
from . import onboarding_workflow, offboarding_workflow

from . import is_user_able_to_upload_to_cloud

from . import help_send_new_token, help_more_help
from . import app_uri

from . import media_urls

from . import envars

from . import imgbb

from . import escape_markdown


telegram_base_api_url = 'https://api.telegram.org'
telegram_api_url = f"{telegram_base_api_url}/{envars.telegram_full_token}"

provider = 'telegram'

# These messages require special treatment
command_list = [
    '/start',
    "/help",
    "/refresh",
    "/token_refresh",
    "/token_refresh_confirm",
    "/more_help",
    "/readme",
    "/delete_account",
    "/delete_account_confirm",
]

supported_message_types = [
    "text",
    "photo",
    "location",
]


def download_file_from_telegram(
        file_path,
        extension="jpg",
        save_name=None
):

    if not save_name:
        # Create a random save name if one is not provided
        save_name = secrets.token_hex(16) + "." + extension

    # Download the file
    url = f"{telegram_base_api_url}/file/{envars.telegram_full_token}/{file_path}"
    r = requests.get(url)

    if r.status_code == 200:
        file_save_path = f"{media_uploads_folder}/{save_name}"
        with open(file_save_path, 'wb') as f:
            f.write(r.content)
        logging.info("File successfully downloaded from Telegram")

        return save_name
    else:
        logging.error("Error downloading file from Telegram")
        return False


def send_telegram_message(
        telegram_chat_id,
        message_contents,
        disable_notification=False,
):
    # This sends a message from the server to the Telegram user

    message_contents = escape_markdown(message_contents)

    payload = {
        'chat_id': telegram_chat_id,
        'text': message_contents,
        'parse_mode': 'MarkdownV2',
        'disable_notification': disable_notification
    }
    url = telegram_api_url + '/sendMessage'

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        logging.info("Message sent to Telegram webhook")
        return True
    else:
        logging.error("Error sending message to Telegram user")
        return False


def send_telegram_picture_message(
        telegram_chat_id,
        image_url,
        animation=False,
        caption=None,
):

    payload = {
        'chat_id': telegram_chat_id,
    }
    if caption:
        payload['caption'] = caption

    if animation:
        payload['animation'] = image_url
        url = telegram_api_url + '/sendAnimation'
    else:
        payload['photo'] = image_url
        url = telegram_api_url + '/sendPhoto'

    response = requests.post(url, json=payload)
    logging.info("Message sent to Telegram webhook")
    if response.status_code == 200:
        return True
    else:
        return False


@app.post('/telegram/webhook/')
def telegram_webhook():

    if request.method == 'POST':

        # Check the headers
        auth_token_received_from_webhook = request.headers.get(
            'X-Telegram-Bot-Api-Secret-Token')

        if not auth_token_received_from_webhook:
            logging.error("No auth token received from Telegram webhook")
            return {
                'status': 'error',
                'message': 'No webhook verification token received'
            }, 401

        if auth_token_received_from_webhook != envars.telegram_webhook_auth:
            logging.error(
                "Token " + auth_token_received_from_webhook + " did not match expected")
            return {
                'status': 'error',
                'message': 'Webhook verification token did not match expected'
            }, 401

        # Get the message from the user
        data = request.get_json()

        # Check if this update contains a message, and if not ignore it
        if 'message' not in data:
            logging.info("There is no message in the data received")
            return "nothing to do"

        # Start putting the mandatory fields into the message_received dictionary, return an error if there's a problem
        try:
            message_received = {
                'telegram_message_id': data['message']['message_id'],
                'telegram_chat_id': data['message']['chat']['id'],
                'mobile': data['message']['from']['id'],
            }
        except:
            logging.error("Error parsing JSON received from Telegram")
            return {
                'status': 'error',
                'message': 'JSON received from Telegram webhook could not be parsed'
            }, 401

        # Check if this is a new user and if so run the onboarding workflow
        user = User.query.filter_by(
            provider_id=message_received['telegram_chat_id']).first()
        if not user:
            if 'text' in data['message']:
                new_user_message_contents = data['message']['text']
                if new_user_message_contents.startswith('/start'):
                    beta_code_provided = new_user_message_contents[7:].strip()

                    result = onboarding_result = onboarding_workflow(
                        provider=provider,
                        provider_id=message_received['telegram_chat_id'],
                        beta_code=beta_code_provided,
                    )
                    if result:
                        logging.info("New user successfully onboarded")
                        return "ok", 200
                    else:
                        logging.error("Error onboarding user")
                        return "error onboarding", 400
                send_message(
                    provider=provider,
                    provider_id=message_received['telegram_chat_id'],
                    contents=message_string['start_with_start_please']
                )
                return "done"

        # If it's not a new user, process the message and add it to the database
        if user:

            # Work out the message type and get the relevant information
            result = False

            if 'text' in data['message']:
                message_received['message_type'] = 'text'
                message_received['message_contents'] = data['message']['text']

                # Check if this is a command (other than /start, which is handled above)
                if message_received['message_contents'].startswith('/'):

                    # Split the command into the base command (eg /help) and any argument (eg /help more)
                    command_contents = message_received['message_contents'].split(
                        " ")
                    command = str(command_contents[0]).lower()
                    argument = str(command_contents[1]).lower() if len(
                        command_contents) > 1 else None

                    if command == '/help':
                        result = send_message(
                            provider,
                            message_received['telegram_chat_id'],
                            message_string['telegram_help_message']
                        )

                    if command == '/token_refresh':
                        result = send_message(
                            provider,
                            message_received['telegram_chat_id'],
                            f"{message_string['danger_zone']}^^{message_string['confirm_refresh_token']}{message_string['confirm_refresh_token_telegram_suffix']}"
                        )

                    if command == '/token_refresh_confirm':
                        result = help_send_new_token(
                            user.id, provider, message_received['telegram_chat_id'])

                    if command == "/more_help":
                        result = help_more_help(
                            user.id, provider, message_received['telegram_chat_id'])

                    if command == "/delete_account":
                        result = send_message(
                            provider,
                            message_received['telegram_chat_id'],
                            f"{message_string['danger_zone']}^^{message_string['confirm_delete_account']}{message_string['confirm_delete_account_telegram_suffix']}"
                        )

                    if command == "/imgbb":
                        if not argument:
                            result = send_message(
                                provider,
                                message_received['telegram_chat_id'],
                                message_string['imgbb_no_argument']
                            )
                        if argument:
                            if imgbb.api_key_valid(argument):
                                user.imgbb_api_key = argument
                                db.session.commit()
                                result = send_message(
                                    provider,
                                    message_received['telegram_chat_id'],
                                    message_string['imgbb_key_set']
                                )
                                send_picture_message(
                                    provider,
                                    message_received['telegram_chat_id'],
                                    media_urls['toast'],
                                    animation=True
                                )
                            else:
                                result = send_message(
                                    provider,
                                    message_received['telegram_chat_id'],
                                    message_string['imgbb_invalid_key']
                                )
                                send_picture_message(
                                    provider,
                                    message_received['telegram_chat_id'],
                                    media_urls['sad_pam'],
                                    animation=True
                                )

                    if message_received['message_contents'] == "/delete_account_confirm":
                        result = offboarding_workflow(
                            provider, message_received['telegram_chat_id'])

                    if not result:
                        result = send_message(
                            provider,
                            message_received['telegram_chat_id'],
                            message_string["sorry_didnt_understand_command"]
                        )
                        send_message(
                            provider,
                            message_received['telegram_chat_id'],
                            message_string['telegram_help_message']
                        )

                else:
                    # Add the message to the database
                    result = add_new_message(
                        user_id=user.id,
                        provider=provider,
                        message_contents=message_received['message_contents'],
                        provider_message_id=message_received['telegram_message_id'],
                    )

            if 'photo' in data['message']:

                if 'photo' in data['message']:
                    message_received['message_type'] = 'photo'
                    message_received['file_id'] = data['message']['photo'][-1]['file_id']

                # if 'video' in data['message']:
                # message_received['message_type'] = 'video'
                # message_received['file_id'] = data['message']['video']['file_id']
                # message_received['file_name'] = f"{secrets.token_hex(6)}{['message']['video']['file_name']}"

                # Get the caption if there is one
                if 'caption' in data['message']:
                    message_received['caption'] = data['message']['caption']
                else:
                    message_received['caption'] = None

                # Download the file from telegram

                # Get the file path from the Telegram API
                r = requests.get(
                    telegram_api_url + '/getFile?file_id=' + message_received['file_id'])
                message_received['file_path'] = r.json()['result']['file_path']

                # Download the file from Telegram
                download_result = False
                if message_received['message_type'] == 'photo':
                    download_result = download_file_from_telegram(
                        file_path=message_received['file_path'],
                        extension="jpg",
                    )
                # if message_received['message_type'] == 'video':
                # download_result = download_file_from_telegram(
                # file_path=message_received['file_path'],
                # save_name=message_received['file_name'],
                # )

                if download_result:
                    message_received['local_file_name'] = download_result
                    message_received['local_file_path'] = f"{media_uploads_folder}/{download_result}"

                    # Check the user can upload this type of file
                    if is_user_able_to_upload_to_cloud(user.id):
                        # Add the message to the database
                        message_received['message_contents'] = compose_image_message_contents(
                            image_file_path=message_received['local_file_path'],
                            imgbb_api_key=user.imgbb_api_key,
                            caption=message_received['caption']
                        )
                        if message_received['message_contents']:
                            result = add_new_message(
                                user_id=user.id,
                                provider=provider,
                                message_contents=message_received['message_contents'],
                                provider_message_id=message_received['telegram_message_id']
                            )
                        else:
                            logging.error("Failed to upload image to cloud")
                    else:
                        logging.error("User cannot upload to cloud")
                        result = send_message(
                            provider,
                            message_received['telegram_chat_id'],
                            message_string['cannot_upload_to_cloud']
                        )
                else:
                    logging.error("Error downloading file from Telegram")

            if 'location' in data['message']:
                message_received['message_type'] = 'location'
                message_received['location_latitude'] = data['message']['location']['latitude']
                message_received['location_longitude'] = data['message']['location']['longitude']

                if "venue" in data['message']:
                    message_received['location_title'] = data['message']['venue'].get(
                        'title')
                    message_received['location_address'] = data['message']['venue'].get(
                        'address')
                else:
                    message_received['location_title'] = None
                    message_received['location_address'] = None

                # Add the message to the database
                message_received['message_contents'] = compose_location_message_contents(
                    location_latitude=message_received['location_latitude'],
                    location_longitude=message_received['location_longitude'],
                    location_name=message_received['location_title'],
                    location_address=message_received['location_address']
                )

                result = add_new_message(
                    user_id=user.id,
                    provider=provider,
                    message_contents=message_received['message_contents'],
                    provider_message_id=message_received['telegram_message_id'],
                )

            if 'document' in data['message']:
                send_message(
                    provider,
                    message_received['telegram_chat_id'],
                    message_string['message_type_not_supported']
                )
                result = True

            # If message type has not been set then return an error
            if result:
                logging.info("Message successfully handled")
                return "ok", 200
            else:
                logging.error(
                    "Failed to add message to database in a way that was unhandled")
                send_message(
                    provider, message_received['telegram_chat_id'], message_string["error_with_message"])
                return "Failed to add message to database", 400


def check_webhook_health():

    url = f"{telegram_api_url}/getWebhookInfo"

    try:
        r = requests.get(url)
        response_json = r.json()
    except:
        return False

    return {
        'status': response_json['ok'],
        'pending_update_count': response_json['result']['pending_update_count']
    }
