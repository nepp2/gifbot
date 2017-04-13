from configobj import ConfigObj
from slackclient import SlackClient
from gif_bot.GifStore import GifStore
import time
import random

class GifBot:
	def __init__(self, filename):
		config = ConfigObj(filename)
		self.NAME      = config["bot_name"]
		self.OWNER     = config["bot_owner"]
		self.API_TOKEN = config["api_token"]
		self.MANIFEST  = config["manifest_loc"]
		# Initialise the store of GIFs
		self.store = GifStore(open(self.MANIFEST).read())
		# Initialise some strings. This should probably be read from a file rather than hard-coded...
		self.collectivenouns = [
			"buddy", "pal", "friend", "friend-o", "mate", "chum", 
			"you awesome person", "you lovely person"
		]
		self.greetings = [
			"Here you go, {}!", "Look after yourself, {}!", "You're fantastic, {}!",
			"I hope you enjoy this, {}! :D", "This is just for you, {}!",
			"One gif coming up! I selected it especially for you, {}!",
			"It's not like I selected this just for you! B-b-baka! :anger: :heart:",
			"I didn't find this gif for you, you know! :anger: :heart:",
			"I hope this helps!",
			"This is for you... I hope you like it... :blush:"
		]
		# Initialise the Slack client
		self.client = SlackClient(self.API_TOKEN)
		# Find out the bot's ID
		api_call = self.client.api_call("users.list")
		if api_call.get("ok"):
			set_bot_id = False
			set_owner_id = False
			for user in api_call["members"]:
				if "name" in user and user["name"] == self.NAME:
					self.BOT_ID = user["id"]
					set_bot_id = True
				if "name" in user and user["name"] == self.OWNER:
					self.OWNER_ID = user["id"]
					set_owner_id = True
			if not set_bot_id:
				self.log("error", "Unable to find user \"" + self.NAME + "\" in the Slack channel")
				raise Exception()
			if not set_owner_id:
				self.log("error", "Unable to find user \"" + self.OWNER + "\" in the Slack channel")
				raise Exception()
		else:
			self.log("error", "Error in API call to users.list")
			raise Exception()
	
	def run(self):
		STD_DELAY = 0.5
		ERR_DELAY = 5
		MAX_DELAY = 3600
		while True:
			try:
				if self.client.rtm_connect():
					self.log("status", "Bot connected")
					while True:
						rtm_messages = self.client.rtm_read()
						self.handle(rtm_messages)
						time.sleep(STD_DELAY)
				else:
					self.log("error", "Bot is unable to connect to the Slack service")
			except:
				self.log("error", "Unknown exception encountered.")
			if (ERR_DELAY < MAX_DELAY):
				self.log("status", "Trying again in " + str(ERR_DELAY) + " seconds...")
				time.sleep(ERR_DELAY)
				ERR_DELAY *= 2
			else:
				self.log("error", "Maximum number of exceptions caught. Exiting...")
				return
		
	def handle(self, rtm_messages):
		if rtm_messages and len(rtm_messages) > 0:
			for message in rtm_messages:
				# self.log("input", "Received " + message["type"])
				if message["type"] == "message":
					self.handle_message(message)
	
	def handle_message(self, message):
		if "user" not in message:
			return
		if message["user"] == self.BOT_ID:
			return
		elif message["user"] == self.OWNER_ID and message["channel"][0] == "D":
			self.handle_command(message["text"], message["channel"])
		elif self.is_mention(message["text"]):
			self.handle_mention(message["text"], message["channel"])
		elif self.gif_trigger(message["text"]):
			self.post_gif(message["channel"])
	
	def is_mention(self, text):
		return "@" + self.BOT_ID in text
	
	def post_message(self, text, channel):
		self.client.api_call("chat.postMessage", channel=channel, text=text, as_user=True)
	
	def handle_command(self, text, channel):
		tokens = text.split(" ")
		if len(tokens)==0:
			return
		if tokens[0] == "add" and len(tokens) > 1:
			self.store.add_gif(tokens[1][1:-1], tokens[2:])
			self.post_message(text="Adding " + tokens[1], channel=channel)
			self.post_message(text="> " + tokens[1], channel=channel)
			self.post_message(text="Type `save` to save this to the manifest", channel=channel)
		elif tokens[0] == "remove" and len(tokens) == 2:
			self.store.remove_gif(tokens[1])
			self.post_message(text="Removing " + tokens[1], channel=channel)
		elif tokens[0] == "status":
			self.post_message(text=self.store.get_info(max=10), channel=channel)
		elif tokens[0] == "request":
			if len(tokens) > 1:
				self.post_gif(channel=channel, type=tokens[1])
			else:
				self.post_gif(channel=channel)
		elif tokens[0] == "reload":
			self.store.__init__(open(self.MANIFEST).read())
		elif tokens[0] == "save":
			self.store.save_manifest(self.MANIFEST)
			self.post_message(text="Manifest saved", channel=channel)
		else:
			self.post_message(text="Sorry, I don't understand that command. :/", channel=channel)
			self.post_message(text="Supported commands:\n" \
			                       "`add url token1 token2...`\n" \
			                       "`remove url`\n" \
			                       "`status`\n" \
			                       "`request cat`\n" \
			                       "`reload`\n" \
			                       "`save`", channel=channel)
	
	def handle_mention(self, text, channel):
		tokens = text.split(" ")
		if tokens[0] != "<@" + self.BOT_ID + ">":
			return
		elif len(tokens) == 2 and tokens[1] == "help":
			text="Known commands:\n" \
			     "`help` : Display self message\n" \
			     "`status` : Give a status report of the bot\n" \
			     "`request cat` : Request a cat GIF"
			self.post_message(text=text, channel=channel)
		elif len(tokens) == 2 and tokens[1] == "status":
			self.post_message(text=self.store.get_info(max=10), channel=channel)
		elif len(tokens) == 3 and tokens[1] == "request":
			self.post_gif(channel, tokens[2])
		else:
			self.post_message(text="Sorry, I don't understand that. :/\n" \
			                       "HINT: try `@" + self.NAME + " help`",
			                  channel=channel)
	
	def gif_trigger(self, text):
		return "help" in text.lower()
	
	def post_gif(self, channel, type="all"):
		if type != "all" and not type in self.store.get_tags():
			self.post_message("Sorry, I have no " + type + " gifs... :(", channel=channel)
			return
		for i in range(10):
			self.log("status", "Retrieving gif of type " + type)
			url = self.store.get_gif(type)
			if url:
				text = random.choice(self.greetings).format(random.choice(self.collectivenouns)) + " " + url
				self.post_message(text=text, channel=channel)
				return
		self.log("error", "Unable to find a gif of type " + type + " :(")

	def log(self, type, message):
		msg = "{} {} {}".format(time.strftime("%Y%m%d %H:%M:%S", time.gmtime()),
		                        ("[" + type.upper() + "]").ljust(8),
		                        message)
		print(msg)
