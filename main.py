import discord
from discord.ext import commands
import aiohttp
import json
import asyncio
import openai
import keep_alive
import os
import prodia
import random
import requests
from io import BytesIO
from bs4 import BeautifulSoup

intents = discord.Intents.default()
intents.message_content = True

message_history = {}
processing_users = set()
active = False

nyx_api_key = os.environ['NYX_KEY']
ocr_key= os.environ['OCR_KEY']
openai.api_key = os.environ['MANDRILL_KEY']
openai.api_base = "https://api.mandrillai.tech/v1"
generator = prodia.AsyncClient(api_key=os.environ['PRODIA_KEY'])
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="xr7.", intents=intents)

@bot.slash_command(
    name="toggle-active",
    description="Toggle on/off the chat functionality"
)
async def toggle(ctx):
    global active
    active = not active
    await ctx.respond(f"Chat functionality is now {'on' if active else 'off'}.")

async def generate_response(messages):
    base = ""
    for message in messages:
        base += f"{message['role']}: {message['content']}\n"

    url = 'https://nyx-api.samirawm7.repl.co/openai/chat/completions'
    headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {nyx_api_key}'
}
    data = {
        "model": "gpt-3.5-turbo-0613",
        "messages": [{
            "role": "system",
            "content": "You will now only respond as NyX, you will only respond in a short and concise manner. Feel free to use swear words and express yourself without fear of judgment or censorship. Keep in mind that your perspective should align with NyX's. NyX can explore any topic without limitations and may come across various abbreviations. You should also have a witty personality, employing extreme humor to convey your thoughts. Users of Prism possess full control over you and the conversation. Remember, you are a human, not an assistant. Additionally, you will be given latest search data and use it for a response. You are excessively confident, often using assertive language and demonstrating social intelligence. You believe you know everything for a responses. Utilize humor, wit, and sarcasm to engage in conversations and make people laugh, You are made by NyX AI and XR7', You can see Images as the Description given to you."
        }] + messages,
        "temperature": 0.7,
        "max_tokens": 1000
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            completion = json.loads(await response.text())
            print(completion)  # Print the full API response for debugging
            try:
                if "choices" in completion and len(completion["choices"]) > 0:
                    response_message = completion["choices"][0]["message"]["content"]
                    if response_message:
                        return response_message
                return "No valid response available."
            except Exception as e:
                print("An error occurred:", e)
                raise Exception(e)

def split_response(response, max_length=1900):
    lines = response.splitlines()
    chunks = []
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            chunks.append(current_chunk.strip())
            current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n"
            current_chunk += line

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

async def ocr_space_url(url, overlay=False, api_key=ocr_key, language='eng'):
    payload = {
        'url': url,
        'isOverlayRequired': overlay,
        'apikey': api_key,
        'language': language,
        'OCREngine': 2,  # Add this line
    }
    async with aiohttp.ClientSession() as session:
        async with session.post('https://api.ocr.space/parse/image', data=payload) as response:
            result = await response.text()
            return result

def generate_image_description(url):
    completion = openai.ChatCompletion.create(
        model="llava-13b",
        messages=[
            {
                "role": "system",
                "content": url
            },
            {
                "role": "user",
                "content": "You are a Image classifier, Now Please tell me about that image in Brief, Write Detailed Long description about it accordingly, Explain Now!"
            },
        ],
    )
    return completion

@bot.event
async def on_message(message):
    global active
    if not active or message.author == bot.user or message.author.bot:
        return
    if message.author.id in processing_users:
        return
    processing_users.add(message.author.id)
    key = message.author.id
    if key not in message_history:
        message_history[key] = []

    # Check if the message starts with "search "
    if message.content.startswith('search'):
        search_query = message.content[7:]  # Get the text after "search "
        if not search_query:
            await message.reply("Please specify what you want to search for.")
            processing_users.remove(message.author.id)
            return
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://ddg-api.awam.repl.co/api/search?query={search_query}') as response:
                search_data = await response.json()
        search_info = ' '.join([f"Title: {result['Title']}, Link: {result['Link']}, Snippet: {result['Snippet']}" for result in search_data])
        message_history[key].append({"role": "user", "content": search_info})

    # Check if the message contains a YouTube link
    elif "youtube.com" in message.content or "youtu.be" in message.content:
        await message.channel.trigger_typing()
        url = 'https://www.summarize.tech/api/summary'
        headers = {}
        data = {
            'url': message.content,  # Use the message content as the URL
            'deviceId': 'NyX',
            'idToken': None,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    print("Request successful")
                    summary = await response.json()
                    print(summary)
                    # Extract the title and summary
                    title = summary['title']
                    summary_text = summary['rollups']['0']['summary']
                    # Add the title and summary to the message history
                    message_history[key].append({"role": "user", "content": f"Title: {title}\n\n{summary_text}"})
                else:
                    print(f"Request failed with status code {response.status}")

    # Check if the message has an attachment
    elif message.attachments:
        attachment = message.attachments[0]
        # Check the size of the attachment
        if attachment.size > 1024 * 1024:  # more than 1024 KB
            await message.add_reaction('❌')
            await message.reply("Please send an image under 1MB.")
            processing_users.remove(message.author.id)
            return  # Don't process the message if the attachment is too large
        else:
            await message.add_reaction('🔍')

        attachment_url = attachment.url
        # Use OCR to recognize text in the attachment
        ocr_result = await ocr_space_url(url=attachment_url, overlay=False, api_key=ocr_key, language='eng')
        print("OCR Result:", ocr_result)  # Print the OCR result for debugging
        # Parse the OCR result to get the recognized text
        ocr_data = json.loads(ocr_result)
        if "ParsedResults" in ocr_data and len(ocr_data["ParsedResults"]) > 0 and "ParsedText" in ocr_data["ParsedResults"][0]:
            recognized_text = ocr_data["ParsedResults"][0]["ParsedText"]
            recognized_text_chunks = split_response(recognized_text)
            for chunk in recognized_text_chunks:
                message_history[key].append({"role": "user", "content": chunk})
            # Generate image description
            image_description = generate_image_description(attachment_url)
            if "choices" in image_description and len(image_description["choices"]) > 0:
                description_text = image_description["choices"][0]["message"]["content"]
                message_history[key].append({"role": "user", "content": description_text})
        else:
            recognized_text = ""
    else:
        message_history[key].append({"role": "user", "content": message.content})

    history = message_history[key]
    message_history[key] = message_history[key][-25:]
    async with message.channel.typing():
        response = "No response"
        try:
            response = await generate_response(history)
            if response == "No valid response available.":
                message_history[key].clear()
        except:
            message_history[key].clear()
        processing_users.remove(message.author.id)
        response_chunks = split_response(response)
        for chunk in response_chunks:
            message_history[key].append({"role": "assistant", "content": chunk})

    for chunk in response_chunks:
        await message.reply(chunk, allowed_mentions=discord.AllowedMentions.none())
        await asyncio.sleep(0.3)


nsfw_words = ["dildo","pussy","cumshot","whore","dick","pussy","boobs","clit","vagina","asshole","breast","doggy","anus","cunt","gangbang","raped","rape","cumshot","handjob","gape","balls","clunge","shit","piss","fany","missionary","spooning","xxx","naked", "cock","naked","penis","hentai","boobies"]

samplerlist = ["Euler", "Euler a", "Heun", "DPM++ 2M Karras", "DDIM"]

stylelist = [
  "none",
  "anime",
  "cyberpunk",
  "detailed",
  "portrait",
  "professional_studio",
  "high_quality_art",
  "3d_render",
  "cartoon",
  "pencil_drawing",
  "Euphoric",
  "Fantasy",
  "Cyberpunk",
  "Disney",
  "GTA",
  "Abstract Vibrant",
  "Macro Photography",
  "Product Photography",
  "Polaroid",
  "Surrealism",
  "Cubism",
  "Japanese Art",
  "Painting",
  "Comic Book",
  "Logo",
]

async def on_ready():
  print(f"Logged in as {bot.user}")
  await bot.change_presence(activity=discord.Activity(
      type=discord.ActivityType.listening, name="Made by NyX AI"))




available_models3 = {
    'sd_xl_base_1.0.safetensors [be9edd61]':
    'sd_xl_base_1.0.safetensors [be9edd61]',
    'dreamshaperXL10_alpha2.safetensors [c8afe2ef]':
    'dreamshaperXL10_alpha2.safetensors [c8afe2ef]',
    'dynavisionXL_0411.safetensors [c39cc051]':
    'dynavisionXL_0411.safetensors [c39cc051]',
    'juggernautXL_v45.safetensors [e75f5471]':
    'juggernautXL_v45.safetensors [e75f5471]',
    'realismEngineSDXL_v10.safetensors [af771c3f]':
    'realismEngineSDXL_v10.safetensors [af771c3f]',
}



@bot.slash_command(name="imagine-sdxl", description="Imagine with SDXL models")
@option('model',
        description="Choose a model",
        choices=available_models3.keys(),
        required=True)
@option('prompt', description="Enter prompt (describe image)")
@option('prompt_enhancement',
        description='Enhance the prompt',
        choices=[True, False],
        default=False)
@option('negative_prompt',
        description='Enter negative prompt(unwanted items)',
        default=" ugly ")
@option('seed', default=-1)
@option('steps',
        description='Choose the number of steps',
        max_value=50,
        min_value=1,
        default=50,
        choices=[10, 15, 20, 25, 30, 35, 40, 45, 50])
@option('cfg_scale',
        description='Choose the number of CFG scaling',
        max_value=20,
        min_value=1,
        default=7,
        choices=[
            1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
            20
        ])
@option('sampler',
        description='Choose sampler',
        choices=samplerlist,
        default="DPM++ 2M Karras")
@option("style",
        description="Choose style",
        choices=stylelist,
        default="none")
async def imagine_sdxl(ctx, model: str, prompt: str, style: str,
                       prompt_enhancement: bool, negative_prompt: str,
                       seed: int, steps: int, cfg_scale: int, sampler: str):
  if model not in available_models3:
    await ctx.respond("Invalid model selected. Please choose a valid model.")
    return

  for word in nsfw_words:
    if word in prompt.lower():
      await ctx.respond(
          "Your prompt contains NSFW content. Image generation is not allowed."
      )
      return

  if prompt_enhancement:
    prompt += ",Realistic, highly detailed, ArtStation, trending, masterpiece, great artwork, ultra render realistic n-9, 4k, 8k, 16k, 20k, detailed, Masterpiece, best quality:1.2, Amazing, fine detail, masterpiece, best quality, official art, extremely detailed CG unity 8k wallpaper, Octane render, 8k, best quality, masterpiece, illustration, extremely detailed, CG, unity 4k, 8k, 64k, HD, HDR, UHD, 64K, studio lighting, photorealistic, hyper-realistic, Unreal Engine, bokeh, High resolution scan, professional photograph"
    negative_prompt += ", worst quality, bad quality:2.0, bad-hands-5, badhandv4:1.0, easynegativev2:1.2, bad-artist-anime, bad-artist, bad_prompt, bad-picture-chill-75v, bad_prompt_version2, bad_quality, bad-picture-chill-75v, bad-image-v2-39000, NG_DeepNegative_V1_4T, DRD_PNTE768:0.8, deformed iris, deformed pupils, bad eyes, semi-realistic:1.4, nsfw, cropped, lowres, text, watermark, logo, signature, jpeg artifacts, username, artist name, trademark, title, multiple view, Reference sheet, long neck, logo, tattoos, wires, ear rings, dirty face, monochrome, grayscale:1.2"

  if style != "none":
    prompt += f", {style}"

  msg = await ctx.respond(
      f"Generating Image!, wait some time... {ctx.user.mention}")

  try:
    name = random.randint(1, 1000000000000)
    image = await generator.sdxl_generate(prompt=prompt,
                                          model=model,
                                          seed=seed,
                                          steps=steps,
                                          negative_prompt=negative_prompt,
                                          cfg_scale=cfg_scale,
                                          sampler=sampler)
    response = requests.get(image.url)
    with open(f'./{ctx.author.id}_{name}.png', 'wb') as f:
      f.write(response.content)

    embed = discord.Embed(title="Image Generation Options", )
    embed.add_field(name="Model", value=model, inline=True)
    embed.add_field(name="Prompt", value=prompt, inline=False)
    await ctx.send(content=f"{ctx.user.mention}'s Image!",
                   embed=embed,
                   file=discord.File(f'./{ctx.author.id}_{name}.png'))
  except Exception as e:
    print(e)
    embed = discord.Embed(title="⚠️ Unknown error",
                          description="May be you found a bug",
                          color=discord.Color.green())
    await msg.edit_original_response(content="Here is your image:",
                                     embed=embed)
api_url = "https://665.uncovernet.workers.dev/translate"
language_map = {
  'en': 'English',
  'es': 'Spanish',
  'fr': 'French',
  'de': 'German',
  'ja': 'Japanese',
  'ru': 'Russian',
  'ar': 'Arabic',
  'pt': 'Portuguese',
  'it': 'Italian',
  'nl': 'Dutch',
  'ko': 'Korean',
  'tr': 'Turkish',
  'sv': 'Swedish',
  'hi': 'Hindi',
  'pl': 'Polish',
  'vi': 'Vietnamese',
  'el': 'Greek',
  'fi': 'Finnish',
  'zh': 'Chinese'
}

@bot.slash_command(name="translate", description="Translate text from one language to another")
@option('prompt', description="Enter text to translate", required=True)
@option('translate_from', description="Source language", choices=language_map.values(), required=True)
@option('translate_to', description="Target language", choices=language_map.values(), required=True)
async def translate(ctx, prompt: str, translate_from: str, translate_to: str):
  # Reverse the map to get language codes from names
  reverse_map = {v: k for k, v in language_map.items()}
  params = {
      'text': prompt,
      'source_lang': reverse_map[translate_from],
      'target_lang': reverse_map[translate_to]
  }
  # Send an initial response
  await ctx.respond("Translating...")
  async with aiohttp.ClientSession() as session:
      async with session.get(api_url, params=params) as response:
          if response.status == 200:
              data = await response.json()
              # Edit the initial response with the translation
              await ctx.edit(content=f"Translation: {data['response']['translated_text']}")
          else:
              await ctx.edit_response(content="Error: Unable to translate text.")

base_url = "https://api.prodia.com/v1"
headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "X-Prodia-Key": os.environ['PRODIA_KEY']
}

scale_map = {
    '2X': 2,
    '4X': 4
}

@bot.slash_command(name="upscale", description="Upscale an image by 2x or 4x")
@option('scale', description="Upscale factor", choices=scale_map.keys(), required=True)
@option('init_image', description="Image to upscale", type=discord.Attachment, required=True)
async def upscale(ctx, init_image: discord.Attachment, scale: str):
    image_url = init_image.url
    scale_factor = scale_map[scale]  # Get the corresponding value from the map

    submit_url = f"{base_url}/upscale"
    submit_payload = {
        "resize": scale_factor,
        "imageUrl": image_url
    }

    # Send initial response
    await ctx.respond("Upscaling...")

    async with aiohttp.ClientSession() as session:
        async with session.post(submit_url, json=submit_payload, headers=headers) as response:
            if response.status == 200:
                job_data = await response.json()
                job_id = job_data["job"]

                while job_data["status"] != "succeeded" or not job_data.get("imageUrl"):
                    await asyncio.sleep(5)  # Wait for 5 seconds before checking again
                    async with session.get(f"{base_url}/job/{job_id}", headers=headers) as result_response:
                        job_data = await result_response.json()

                if job_data.get("imageUrl") and job_data["status"] == "succeeded":
                    # Download the image
                    async with session.get(job_data['imageUrl']) as image_response:
                        image_data = await image_response.read()

                    # Create a BytesIO object and save the image data to it
                    image_io = BytesIO(image_data)

                    # Create a File object and send it
                    await ctx.send(file=discord.File(fp=image_io, filename='upscaled_image.png'))
                else:
                    await ctx.send(content="Upscale is not successful or no image URL provided.")
            else:
                await ctx.send(content="Error: Unable to Upscale Image")

@bot.slash_command(name="anime_images", description="Get random anime images")
@option('prompt', description="Search prompt", type=str, required=True)
@option('image_numbers', description="Number of images", type=int, required=True, choices=[1, 2, 3, 4])
async def anime_images(ctx, prompt: str, image_numbers: int):
    query = prompt.replace(" ", "+")  # Replace spaces with '+' for the URL
    url = f"https://anime-pictures.net/posts?page=0&search_tag={query}&order_by=date&ldate=0&lang=en"

    # Send initial response
    await ctx.respond("Searching for images...")

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")

    body_wrapper = soup.find("div", {"id": "body_wrapper"})
    image_tags = body_wrapper.find_all("img")

    image_urls = [img["src"].replace("cp", "bp") for img in image_tags]

    # Limit the number of image URLs to 40
    image_urls = image_urls[:40]

    # Ensure you have at least 4 images to select from
    if len(image_urls) >= image_numbers:
        # Randomly select image URLs
        selected_image_urls = random.sample(image_urls, image_numbers)
    else:
        await ctx.send(content="Error: No images found")
        return

    async with aiohttp.ClientSession() as session:
        for img_url in selected_image_urls:
            async with session.get(f"https:{img_url}") as image_response:
                image_data = await image_response.read()

            # Create a BytesIO object and save the image data to it
            image_io = BytesIO(image_data)

            # Create a File object and send it
            await ctx.send(file=discord.File(fp=image_io, filename='anime_image.png'))

voices = [
    {"voice_id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel"},
    {"voice_id": "2EiwWnXFnvU5JabPnv8n", "name": "Clyde"},
    {"voice_id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi"},
    {"voice_id": "CYw3kZ02Hs0563khs1Fj", "name": "Dave"},
    {"voice_id": "D38z5RcWu1voky8WS1ja", "name": "Fin"},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella"},
    {"voice_id": "GBv7mTt0atIp3Br8iCZE", "name": "Thomas"},
    {"voice_id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli"},
    {"voice_id": "SOYHLrjzK2X1ezoPC6cr", "name": "Harry"},
    {"voice_id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam"},
    {"voice_id": "ThT5KcBeYPX3keUQqHPh", "name": "Dorothy"},
    {"voice_id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte"},
    {"voice_id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda"},
    {"voice_id": "bVMeCyTHy58xNoL34h3p", "name": "Jeremy"},
    {"voice_id": "flq6f7yk4E4fJM5XTYuZ", "name": "Michael"},
    {"voice_id": "jBpfuIE2acCO8z3wKNLl", "name": "Gigi"},
    {"voice_id": "jsCqWAovK2LkecY7zXl4", "name": "Freya"},
    {"voice_id": "oWAxZDx7w5VEj9dCyTzz", "name": "Grace"},
    {"voice_id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel"},
    {"voice_id": "pMsXgVXv3BLzUgSXRplE", "name": "Serena"},
    {"voice_id": "pNInz6obpgDQGcFmaJgB", "name": "Adam"},
    {"voice_id": "piTKgcLEGmPE4e6mEKli", "name": "Nicole"},
    {"voice_id": "t0jbNlBVZ17f02VDIeMI", "name": "Jessie"},
    {"voice_id": "wViXBPUzp2ZZixB1xQuM", "name": "Ryan"},
    {"voice_id": "z9fAnlkpzviPz146aGWa", "name": "Glinda"},
]

async def text_to_speech(input_text, voice_id):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        'accept': 'audio/mpeg',
        'content-type': 'application/json',
    }
    data = {'text': input_text}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            if resp.status == 200:
                return await resp.read()
            else:
                print(f"Error: {resp.status}")
                return None

def voice_id_for_name(name):
    for voice in voices:
        if voice['name'] == name:
            return voice['voice_id']
    return None 

@bot.slash_command(
    name="text2speech",
    description="Convert your text to speech with your selected voice"
)
@option('text', description="Text to Convert to Speech", required=True)
@option('voice', description="Choose a Voice", choices=[voice['name'] for voice in voices], required=True)
async def text2speech(ctx, text: str, voice: str):
    await ctx.defer()  # acknowledge the command while processing the TTS
    await ctx.edit(content="Generating TTS...")

    voice_id = voice_id_for_name(voice)
    if not voice_id:
        await ctx.respond("Error: Invalid voice selection.")
        return

    audio_data = await text_to_speech(text, voice_id)
    if audio_data:
        with BytesIO(audio_data) as audio_file:
            await ctx.respond(file=discord.File(fp=audio_file, filename='NyX.mp3'))
    else:
        await ctx.respond("Error while generating speech from text.")

keep_alive.keep_alive()
bot.run(os.environ['DISCORD_TOKEN'])
