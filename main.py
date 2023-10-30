import discord
from discord.ext import commands
import aiohttp
import json
import asyncio
import os
import openai
import keep_alive
import os
import keep_alive
import discord
import os
from discord.ext import commands
from discord import option
import keep_alive
import prodia
import random
import requests
from datetime import datetime, timedelta
import base64
import datetime
from io import BytesIO

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


keep_alive.keep_alive()
bot.run(os.environ['DISCORD_TOKEN'])
