import logging
import secrets
import requests
import pprint # for debug
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response

from __main__ import app
from __main__ import random_token
from __main__ import create_new_user, add_new_message, compose_location_message_contents, compose_image_message_contents

from __main__ import db
from __main__ import User

from __main__ import whitelist_only, message_string

import secretstuff

telegram_api_url = f"https://api.telegram.org/{secretstuff.telegram_full_token}"

provider = 'telegram'


def send_telegram_message(
	telegram_chat_id,
	message_contents
):
	payload = {
		'chat_id': telegram_chat_id,
		'text': message_contents,
	}
	url = telegram_api_url + '/sendMessage'
	response = requests.post(url, json=payload)

	print ("Message sent to " + url + " response code was " + str(response.status_code))

	if response.status_code == 200:
		return True
	else:
		return False



@app.route('/telegram/webhook/', methods=['POST'])
def telegram_webhook():

	if request.method == 'POST':
		# Get the message from the user
		data = request.get_json()
		#pprint.pprint(data)

		# Start putting the mandatory fields into the message_received dictionary, return an error if there's a problem
		try:
			message_received = {
				'telegram_message_id': data['message']['message_id'],
				'telegram_chat_id': data['message']['chat']['id'],
				'mobile': data['message']['from']['id'],
			}
		except:
			return "Error: Telegram message missing mandatory fields"

		# See if this is a new user:
		user = User.query.filter_by(mobile=message_received['mobile']).first()

		# If it is a new user, create the account and return the token
		if not user:
			user = create_new_user(
				account_type="telegram",
				phone_number=message_received['mobile'],
				chat_id=message_received['telegram_chat_id'],
			)
			if not user:
				logging.error("Failed to create new user")
				if whitelist_only:
					send_telegram_message(message_string["problem_creating_user"], message_received['mobile'])
				else:
					send_telegram_message(message_string["problem_creating_user_generic"], message_received['mobile'])
				return "Failed to create new user"

			logging.info("New user: %s", user.phone_number)
			send_telegram_message(message_string["welcome_to_loglink"], message_received['mobile'])
			send_telegram_message(user.token, message_received['mobile'])
			return "ok"

		# If it is not a new user, process the message
		if user:

			# Work out the message type and get the relevant information
			message_type = None
			if 'text' in data['message']:
				message_received['message_type'] = 'text'
				message_received['message_contents'] = data['message']['text']

				# Add the message to the database
				message_id = message_received['telegram_message_id']
				result = add_new_message(
					user_id=user.id,
					received_from="whatsapp",
					message_contents=message_received['message_contents'],
					provider_message_id=message_received['telegram_message_id']
				)

			elif 'photo' in data['message']:
				message_received['message_type'] = 'photo'
				message_received['photo_id'] = data['message']['photo'][0]['file_id']
				if 'caption' in data['message']:
					message_received['caption'] = data['message']['caption']

			pprint.pprint (message_received)

			send_telegram_message(
				message_received['telegram_chat_id'],
				"received"
			)

	return "ok"