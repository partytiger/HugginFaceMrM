#!/usr/bin/env python

import os
import random
import uuid
import json
#import devicetorch


import gradio as gr
import numpy as np
from PIL import Image
import spaces
import torch
from diffusers import DiffusionPipeline
from typing import Tuple

#MrM 20240727 :: added from test script :: START

# Dynamically get the current device name: will return either "cuda", "mps", or "cpu".
device = devicetorch.get(torch)

#pipe_edit = CosStableDiffusionXLInstructPix2PixPipeline.from_single_file(edit_file, num_in_channels=8)
#pipe_edit.scheduler = EDMEulerScheduler(sigma_min=0.002, sigma_max=120.0, sigma_data=1.0, prediction_type="v_prediction")
#pipe_edit.to("cuda")

#pipe_normal = StableDiffusionXLPipeline.from_single_file(normal_file, torch_dtype=torch.float16)
#pipe_normal.scheduler = EDMEulerScheduler(sigma_min=0.002, sigma_max=120.0, sigma_data=1.0, prediction_type="v_prediction")
#pipe_normal.to("cuda")

#MrM 20240727 :: added from test script :: END


#Check for the Model Base..//



bad_words = json.loads(os.getenv('BAD_WORDS', "[]"))
bad_words_negative = json.loads(os.getenv('BAD_WORDS_NEGATIVE', "[]"))
default_negative = os.getenv("default_negative","")

def check_text(prompt, negative=""):
    for i in bad_words:
        if i in prompt:
            return True
    for i in bad_words_negative:
        if i in negative:
            return True
    return False



style_list = [

    {
        "name": "2560 x 1440",
        "prompt": "hyper-realistic 4K image of {prompt}. ultra-detailed, lifelike, high-resolution, sharp, vibrant colors, photorealistic",
        "negative_prompt": "cartoonish, low resolution, blurry, simplistic, abstract, deformed, ugly",
    },

    {
        "name": "Photo",
        "prompt": "cinematic photo {prompt}. 35mm photograph, film, bokeh, professional, 4k, highly detailed",
        "negative_prompt": "drawing, painting, crayon, sketch, graphite, impressionist, noisy, blurry, soft, deformed, ugly",
    },   

    {
        "name": "Cinematic",
        "prompt": "cinematic still {prompt}. emotional, harmonious, vignette, highly detailed, high budget, bokeh, cinemascope, moody, epic, gorgeous, film grain, grainy",
        "negative_prompt": "anime, cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, mutated, ugly, disfigured",
    },

    {
        "name": "Anime",
        "prompt": "anime artwork {prompt}. anime style, key visual, vibrant, studio anime, highly detailed",
        "negative_prompt": "photo, deformed, black and white, realism, disfigured, low contrast",
    },
    {
        "name": "3D Model",
        "prompt": "professional 3d model {prompt}. octane render, highly detailed, volumetric, dramatic lighting",
        "negative_prompt": "ugly, deformed, noisy, low poly, blurry, painting",
    },
    {
        "name": "(No style)",
        "prompt": "{prompt}",
        "negative_prompt": "",
    },
]

styles = {k["name"]: (k["prompt"], k["negative_prompt"]) for k in style_list}
STYLE_NAMES = list(styles.keys())
DEFAULT_STYLE_NAME = "2560 x 1440"

def apply_style(style_name: str, positive: str, negative: str = "") -> Tuple[str, str]:
    p, n = styles.get(style_name, styles[DEFAULT_STYLE_NAME])
    if not negative:
        negative = ""
    return p.replace("{prompt}", positive), n + negative



    

DESCRIPTION = """## MidJourney"""





if not torch.cuda.is_available():
    DESCRIPTION += "\n<p>??Running on CPU, This may not work on CPU.</p>"

MAX_SEED = np.iinfo(np.int32).max
CACHE_EXAMPLES = torch.cuda.is_available() and os.getenv("CACHE_EXAMPLES", "0") == "1"
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE", "2048"))
USE_TORCH_COMPILE = os.getenv("USE_TORCH_COMPILE", "0") == "1"
ENABLE_CPU_OFFLOAD = os.getenv("ENABLE_CPU_OFFLOAD", "0") == "1"

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

NUM_IMAGES_PER_PROMPT = 10

if torch.cuda.is_available():
    pipe = DiffusionPipeline.from_pretrained(
        "SG161222/RealVisXL_V3.0_Turbo",
        torch_dtype=torch.float16,
        use_safetensors=True,
        add_watermarker=False,
        variant="fp16"
    )
    pipe2 = DiffusionPipeline.from_pretrained(
        "SG161222/RealVisXL_V2.02_Turbo",
        torch_dtype=torch.float16,
        use_safetensors=True,
        add_watermarker=False,
        variant="fp16"
    )
    if ENABLE_CPU_OFFLOAD:
        pipe.enable_model_cpu_offload()
        pipe2.enable_model_cpu_offload()
    else:
        pipe.to(device)    
        pipe2.to(device)    
        print("Loaded on Device!")
    
    if USE_TORCH_COMPILE:
        pipe.unet = torch.compile(pipe.unet, mode="reduce-overhead", fullgraph=True)
        pipe2.unet = torch.compile(pipe2.unet, mode="reduce-overhead", fullgraph=True)
        print("Model Compiled!")

def save_image(img):
    unique_name = str(uuid.uuid4()) + ".png"
    img.save(unique_name)
    return unique_name

def randomize_seed_fn(seed: int, randomize_seed: bool) -> int:
    if randomize_seed:
        seed = random.randint(0, MAX_SEED)
    return seed

@spaces.GPU(enable_queue=True)
def generate(
    prompt: str,
    negative_prompt: str = "",
    use_negative_prompt: bool = False,
    style: str = DEFAULT_STYLE_NAME,
    seed: int = 0,
    width: int = 1024,
    height: int = 1024,
    guidance_scale: float = 3,
    randomize_seed: bool = False,
    use_resolution_binning: bool = True,
    progress=gr.Progress(track_tqdm=True),
):
    if check_text(prompt, negative_prompt):
        raise ValueError("Prompt contains restricted words.")
    
    prompt, negative_prompt = apply_style(style, prompt, negative_prompt)
    seed = int(randomize_seed_fn(seed, randomize_seed))
    generator = torch.Generator().manual_seed(seed)

    if not use_negative_prompt:
        negative_prompt = ""  # type: ignore
    negative_prompt += default_negative    

    options = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "guidance_scale": guidance_scale,
        "num_inference_steps": 30,
        "generator": generator,
        "num_images_per_prompt": NUM_IMAGES_PER_PROMPT,
        "use_resolution_binning": use_resolution_binning,
        "output_type": "pil",
    }
    
    images = pipe(**options).images + pipe2(**options).images

    image_paths = [save_image(img) for img in images]
    return image_paths, seed

examples = [
    "Annie Leibovitz tarzinda ve Wes Anderson tarzinda, rustik bir kabinde, sig bir alan derinligine sahip, vintage film grenli, yakin �ekim bir kedinin, bir pencerenin yakin �ekimi. --ar 85:128 --v 6.0 --stil ham",
    "Daria Morgendorffer animasyon serisinin ana karakteri Daria, ciddi ifadesi, �ok heyecan verici sehvetli g�r�n�m�, �ok atesli bir kiz, g�zel karizmatik bir kiz, �ok atesli bir atis, g�zl�k takan bir kadin, muhtesem bir fig�r, ilgin� sekiller, ger�ek boyutlu fig�rler",
    "Koyu yesil b�y�k antoryum yapraklari, yakin �ekim, fotograf, havadan g�r�n�m, unsplash tarzinda, hasselblad h6d400c --ar 85:128 --v 6.0 --style raw",
    "Sarisin kadinin yakin �ekimi alan derinligi, bokeh, sig odak, minimalizm, Canon EF lensli Fujifilm xh2s, sinematik --ar 85:128 --v 6.0 --style raw"
]

css = '''
.gradio-container{max-width: 700px !important}
h1{text-align:center}
'''
with gr.Blocks(css=css, theme="bethecloud/storj_theme") as demo:
    gr.Markdown(DESCRIPTION)
    gr.DuplicateButton(
        value="Duplicate Space for private use",
        elem_id="duplicate-button",
        visible=os.getenv("SHOW_DUPLICATE_BUTTON") == "1",
    )
    with gr.Group():
        with gr.Row():
            prompt = gr.Text(
                label="Prompt",
                show_label=False,
                max_lines=1,
                placeholder="Enter your prompt",
                container=False,
            )
            run_button = gr.Button("Run")
        result = gr.Gallery(label="Result", columns=1, preview=True)
    with gr.Accordion("Advanced options", open=False):
        use_negative_prompt = gr.Checkbox(label="Use negative prompt", value=True, visible=True)
        negative_prompt = gr.Text(
            label="Negative prompt",
            max_lines=1,
            placeholder="Enter a negative prompt",
            value="(deformed iris, deformed pupils, semi-realistic, cgi, 3d, render, sketch, cartoon, drawing, anime:1.4), text, close up, cropped, out of frame, worst quality, low quality, jpeg artifacts, ugly, duplicate, morbid, mutilated, extra fingers, mutated hands, poorly drawn hands, poorly drawn face, mutation, deformed, blurry, dehydrated, bad anatomy, bad proportions, extra limbs, cloned face, disfigured, gross proportions, malformed limbs, missing arms, missing legs, extra arms, extra legs, fused fingers, too many fingers, long neck",
            visible=True,
        )
        with gr.Row():
            num_inference_steps = gr.Slider(
                label="Steps",
                minimum=10,
                maximum=60,
                step=1,
                value=30,
            )
        with gr.Row():
            num_images_per_prompt = gr.Slider(
                label="Images",
                minimum=1,
                maximum=5,
                step=1,
                value=2,
            )
        seed = gr.Slider(
            label="Seed",
            minimum=0,
            maximum=MAX_SEED,
            step=1,
            value=0,
            visible=True
        )
        randomize_seed = gr.Checkbox(label="Randomize seed", value=True)
        with gr.Row(visible=True):
            width = gr.Slider(
                label="Width",
                minimum=512,
                maximum=2048,
                step=8,
                value=1024,
            )
            height = gr.Slider(
                label="Height",
                minimum=512,
                maximum=2048,
                step=8,
                value=1024,
            )
        with gr.Row():
            guidance_scale = gr.Slider(
                label="Guidance Scale",
                minimum=0.1,
                maximum=20.0,
                step=0.1,
                value=6,
            )
    with gr.Row(visible=True):
        style_selection = gr.Radio(
            show_label=True,
            container=True,
            interactive=True,
            choices=STYLE_NAMES,
            value=DEFAULT_STYLE_NAME,
            label="Image Style",
        )
    gr.Examples(
        examples=examples,
        inputs=prompt,
        outputs=[result, seed],
        fn=generate,
        cache_examples=CACHE_EXAMPLES,
    )

    use_negative_prompt.change(
        fn=lambda x: gr.update(visible=x),
        inputs=use_negative_prompt,
        outputs=negative_prompt,
        api_name=False,
    )

    gr.on(
        triggers=[
            prompt.submit,
            negative_prompt.submit,
            run_button.click,
        ],
        fn=generate,
        inputs=[
            prompt,
            negative_prompt,
            use_negative_prompt,
            style_selection,
            seed,
            width,
            height,
            guidance_scale,
            randomize_seed,
        ],
        outputs=[result, seed],
        api_name="run",
    )

if __name__ == "__main__":
    demo.queue(max_size=30).launch()
