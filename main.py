from instagrapi import Client, exceptions
from telegram import Update, constants, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackContext
from urllib.request import build_opener
from urllib.parse import urlparse
import json, os, re, base64, pathlib, shutil

def get_shortcode(url):
    rgx = re.findall(r'https:\/\/www.instagram.com\/(?:reel|p)\/([^?\/]*)',url)
    if len(rgx) != 0:
        return rgx[0]
    return None

def shortcode_to_id(shortcode):
    code = ('A' * (12-len(shortcode))) + shortcode
    return int.from_bytes(base64.b64decode(code.encode(), b'-_'), 'big')

def get_media_urls(post):
    media_urls = []
    if post['media_type'] == 1:
        media_urls.append({'type': 'image', 'url': post['thumbnail_url']})
    elif post['media_type'] == 2:
        media_urls.append({'type': 'video', 'url': post['video_url']})
    elif post['media_type'] == 8:
        for media in post['resources']:
            media_urls += get_media_urls(media)
    return media_urls

class IGClient:
    username = ''
    password = ''
    client = None

    def __init__(self, username, password) -> None:
        self.username = username
        self.password = password
        self.session_location = f'accounts/{self.username}.json'
        self.set_ig_client()
        self.check_session()
    
    def check_session(self):
        try:
            print(f'Using account {self.client.account_info().username}')
        except exceptions.LoginRequired:
            os.remove(self.session_location)
            self.set_ig_client()

    def set_ig_client(self):
        self.client = Client()
        if os.path.exists(self.session_location):
            self.client.load_settings(self.session_location)
        
        try:
            self.client.login(self.username, self.password)
        except (exceptions.UnknownError, exceptions.BadPassword):
            if self.client.last_json['invalid_credentials']:
                print(f'incorrect username or password.')
            exit()

        if not os.path.exists(self.session_location):
            self.client.dump_settings(self.session_location)

    def get_media_info(self, shortcode) -> dict:
        media_id = shortcode_to_id(shortcode)
        
        try:
            result = self.client.media_info(media_id)
        except exceptions.PleaseWaitFewMinutes:
            raise Exception('Please resend your media a few minutes later!')
        
        return json.loads(result.model_dump_json())

async def download_handler(update: Update, context: CallbackContext) -> None:
    shortcode = get_shortcode(update.message.text)
    if shortcode == None:
        await update.message.reply_text('invalid url!', parse_mode=constants.ParseMode.HTML)
        return

    await update.message.reply_text('Getting info ...', reply_to_message_id=update.message.id)

    try:
        info = ig_client.get_media_info(shortcode)
    except Exception as e:
        await update.message.reply_text(str(e), reply_to_message_id=update.message.id)
        return
        
    media = get_media_urls(info)
    await update.message.reply_text('Downloading media...', reply_to_message_id=update.message.id)
    
    media_id = shortcode_to_id(shortcode)
    pathlib.Path(f'media/{media_id}').mkdir(parents=True, exist_ok=True)
    opener = build_opener()
    media_album = []
    for m in media:
        a = urlparse(m['url'])
        file_name = os.path.basename(a.path)
        if m['type'] == 'image':
            ext = pathlib.Path(file_name).suffix
            file_name = file_name.replace(ext, '.jpg')
        
        with opener.open(m['url']) as response, open(f'media/{media_id}/{file_name}', 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        
        if m['type'] == 'image':
            media_album.append(InputMediaPhoto(open(f'media/{media_id}/{file_name}', 'rb')))
        else:
            media_album.append(InputMediaVideo(open(f'media/{media_id}/{file_name}', 'rb')))

    await update.message.reply_media_group(caption=info['caption_text'], media=media_album, reply_to_message_id=update.message.id)

    shutil.rmtree(f'media/{media_id}')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Welcome! Send link of a post to download", reply_to_message_id=update.message.id)

if __name__ == '__main__':
    with open('config.json','r') as f:
        config = json.loads(f.read())
    
    ig_client = IGClient(config['ig_username'], config['ig_password'])
    application = ApplicationBuilder().token(config['bot_token']).build()

    print('starting ...')
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex(r'https:\/\/www.instagram.com\/(?:reel|p)\/([^?\/]*)'), download_handler))
    application.run_polling()