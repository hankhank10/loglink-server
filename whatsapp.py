import logging
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response

from __main__ import app
from __main__ import whatsapp_messenger, random_token
from __main__ import create_new_user, add_new_message, compose_location_message_contents, compose_image_message_contents

from __main__ import db
from __main__ import User, Message

from __main__ import whitelist_only, delete_immediately, app_uri, message_string
from __main__ import whatsapp_api_messages_uri

import secretstuff


#####################
# WHATSAPP          #
#####################

@app.route('/whatsapp/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == secretstuff.whatsapp_verify_token:
            logging.info("Verified webhook")
            response = make_response(request.args.get("hub.challenge"), 200)
            response.mimetype = "text/plain"
            return response
        logging.error("Webhook Verification failed")
        return "Invalid verification token"

    data = request.get_json()
    # logging.info("Received webhook data: %s", data)

    changed_field = whatsapp_messenger.changed_field(data)
    if changed_field == "messages":
        new_message = whatsapp_messenger.get_mobile(data)
        if new_message:

            # Get all the details of the sender
            mobile = whatsapp_messenger.get_mobile(data)
            name = whatsapp_messenger.get_name(data)
            message_type = whatsapp_messenger.get_message_type(data)

            logging.info(
                f"New Message; sender:{mobile} name:{name} type:{message_type}"
            )

            # Check if this is a new user
            user = User.query.filter_by(phone_number=mobile).first()

            # If it is a new user, create the account and return the token
            if not user:
                user = create_new_user(
                    account_type="whatsapp",
                    phone_number=mobile
                )
                if not user:
                    logging.error("Failed to create new user")
                    if whitelist_only:
                        whatsapp_messenger.send_message(message_string["problem_creating_user"], mobile)
                    else:
                        whatsapp_messenger.send_message(message_string["problem_creating_user_generic"], mobile)
                    return "Failed to create new user"

                logging.info("New user: %s", user.phone_number)
                whatsapp_messenger.send_message(message_string["welcome_to_loglink"], mobile)
                whatsapp_messenger.send_message(user.token, mobile)
                return "ok"

            if user:

                # Set the default to be no result
                result = False

                if message_type == "interactive":
                    message_response = whatsapp_messenger.get_interactive_response(data)
                    interactive_type = message_response.get("type")
                    message_id = message_response[interactive_type]["id"]

                    if message_id == "token_reminder":
                        whatsapp_messenger.send_message(message_string["token_will_be_sent_in_next_message"], mobile)
                        whatsapp_messenger.send_message(user.token, mobile)

                    if message_id == "new_token":
                        user.token = random_token()
                        db.session.commit()
                        whatsapp_messenger.send_message(message_string["resetting_your_token"], mobile)
                        whatsapp_messenger.send_message(message_string["token_reset"], mobile)
                        whatsapp_messenger.send_message(user.token, mobile)

                    if message_id == "more_help":
                        whatsapp_messenger.send_message(message_string["more_help"], mobile)

                    result = True

                if message_type == "text":
                    message_contents = whatsapp_messenger.get_message(data)

                    # Check whether the message contains a command
                    command_list = [
                        "help",
                        "token",
                        "refresh",
                        "readme"
                    ]

                    # Deal with help commands
                    if message_contents.lower() in command_list:
                        whatsapp_messenger.send_reply_button(
                            recipient_id=mobile,
                            button={
                                "type": "button",
                                "header": {
                                    "type": "text",
                                    "text": "LogLink Help"
                                },
                                "body": {
                                    "text": "Did you need some help? If not, no worries you can ignore this message."
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

                    # If the message contains a command only, exit the function so it is not added to the database
                    if message_contents.lower() in command_list:
                        return "ok"

                    # Add the message to the database
                    message_id = whatsapp_messenger.get_message_id(data)
                    result = add_new_message(
                        user_id=user.id,
                        received_from="whatsapp",
                        message_contents=message_contents,
                        whatsapp_message_id=message_id
                    )

                if message_type == "location":
                    message_id = whatsapp_messenger.get_message_id(data)
                    message_location = whatsapp_messenger.get_location(data)

                    # Get the essential location data
                    location_latitude = message_location["latitude"] # always included
                    location_longitude = message_location["longitude"] # always included

                    # Optional fields
                    location_name = message_location.get("name")
                    location_address = message_location.get("address")
                    location_url = message_location.get("url")

                    message_contents = compose_location_message_contents(
                        location_latitude=location_latitude,
                        location_longitude=location_longitude,
                        location_name=location_name,
                        location_address=location_address,
                        location_url=location_url
                    )

                    if message_contents:
                        result = add_new_message(
                            user_id=user.id,
                            received_from="whatsapp",
                            message_contents=message_contents,
                            whatsapp_message_id=message_id
                        )

                if message_type == "image" or message_type == "video":
                    message_id = whatsapp_messenger.get_message_id(data)

                    if message_type == "image":
                        image = whatsapp_messenger.get_image(data)

                    if message_type == "video":
                        image = whatsapp_messenger.get_video(data)

                    image_id, mime_type = image["id"], image["mime_type"]
                    image_url = whatsapp_messenger.query_media_url(image_id)

                    # Get the caption if there is one
                    caption = image.get("caption")

                    # Download the image to a temporary file with a random name
                    uploads_folder = "media_uploads"
                    random_filename = secrets.token_hex(16)
                    random_path = f"{uploads_folder}/{random_filename}"
                    image_filename = whatsapp_messenger.download_media(image_url, mime_type, random_path)

                    message_contents = compose_image_message_contents(
                        image_filename=image_filename,
                        caption = caption
                    )

                    if message_contents:
                        result = add_new_message(
                            user_id=user.id,
                            received_from="whatsapp",
                            message_contents=message_contents,
                            whatsapp_message_id=message_id
                        )
                    else:
                        logging.error("Failed to upload image to imgur")

                unsupported_message_types = [
                    "audio",
                    "file",
                    "document",
                    "contacts",
                    "sticker",
                    "unsupported"
                ]
                if message_type in unsupported_message_types:
                    whatsapp_messenger.send_message(f"Sorry, LogLink does not yet support {message_type} uploads", mobile)
                    result = True

                if result:
                    logging.info("Message added to database")
                    return "ok"
                else:
                    logging.error("Failed to add message to database")
                    return "Failed to add message to database"

    return "no change"
