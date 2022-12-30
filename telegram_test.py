import requests
import logging
import telegram
import pprint


import secretstuff

# Import flask
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response

# Create the app
app = Flask(__name__)

telegram_api_url = f"https://api.telegram.org/{secretstuff.telegram_full_token}"


@app.route('/', methods=['GET'])
def hello_world():
	return 'Hello, World Telegram!'


@app.route('/telegram/webhook/', methods=['GET', 'POST'])
def telegram_webhook():

	if request.method == 'POST':
		# Get the message from the user
		data = request.get_json()
		#pprint.pprint(data)

		telegram_message_id = data['update_id']
		telegram_chat_id = data['message']['chat']['id']
		mobile = data['message']['from']['id']
		message_contents = data['message']['text']

		print ("telegram_message_id: " + str(telegram_message_id))
		print ("telegram_chat_id: " + str(telegram_chat_id))
		print ("mobile: " + str(mobile))
		print ("message_contents: " + str(message_contents))

		send_telegram_message(
			telegram_chat_id,
			"Hello, World Telegram!"
		)

	return "ok"


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


# Run the app
if __name__ == "__main__":
	app.run(host='0.0.0.0', port=5010, debug=True)
