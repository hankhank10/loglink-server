# LogLink

LogLink allows you to add to your LogSeq graph more easily from a variety of sources, with a focus on mobile.

Functioning integrations:
- WhatsApp (beta)

Planned integrations:
- Telegram
- Email
- Discord (maybe)
- Slack (maybe)

## Workflow

The simple workflow is that you send a message from your phone (or desktop) to a number via WhatsApp. You can send text (including special terms like TODO, [[links]] or #hashtags), locations (which resolve nicely including a goodle maps link) or images/videos (which are automatically uploaded to imgur and then inserted into your graph). The service stores these messages until you log into LogSeq on desktop and sync them to your graph via a slash command, at which point they are deleted from the server.

I use this to quickly add to my todo list (eg send a WhatsApp message saying TODO Buy milk or TODO Call [[John Smith]]), send myself quick notes or send images of things I want to remember (eg a photo of a book I want to read).

I am keen to find an intrepid group (5-10) of beta testers to help me test this out. I am even more keen to find anyone keen to collaborate with on this.

If you are interested in either (after reading the important security disclaimer below) then please register interest here: https://5agez8udocf.typeform.com/to/Mlsi9lR7

For potential collaborators, the tech stack is:
- Python/Flask/SQLAlchemy on the backend (which I have covered, although anyone with encryption/security experience would be very welcome);
- JS for the plugin (which I could dearly use some assistance with);
- the front end web app/landing page will be build in HTML+Tailwind (again, help very much appreciated here).

- The service will be free to begin with. I have no aim to run this commercially, although at some point I may have to charge a nominal fee in due course if I start to incur costs (eg for whatsapp or imgur API usage beyond the free plans).

## Security
A  very important note on security: yes, this necessarily does require that messages you send via this pass through the cloud, both Meta's whatsapp API and the server that I run. I have no interest in reading your messages and the code endeavours to delete them as soon as they are delivered but this comes with absolutely no guarantees as to security (or anything else!), and you use it entirely at your own risk.

## Open source
The plugin and the server are both open source, so you are welcome to read the source code (plugin and server github links both below) and you could also use the source code to run your own server.

Plugin code: https://github.com/hankhank10/loglink-plugin