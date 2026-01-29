from fastapi import FastAPI, UploadFile, Form, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List
import shutil, os, uuid, requests, time

app = FastAPI()

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# THƯ MỤC
# =========================
os.makedirs("uploads", exist_ok=True)
os.makedirs("static/generated", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# =========================
# TRANG HTML
# =========================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# =========================
# STABLE HORDE (FREE SD)
# =========================
HORDE_SUBMIT = "https://stablehorde.net/api/v2/generate/async"
HORDE_STATUS = "https://stablehorde.net/api/v2/generate/status/{}"

HEADERS = {
    "Content-Type": "application/json",
    "apikey": "0000000000"  # anonymous
}

def call_stable_horde(prompt: str, output_path: str):
    payload = {
        "prompt": prompt,
        "nsfw": False,
        "models": ["stable_diffusion"],
        "params": {
            "sampler_name": "k_euler",
            "steps": 20,
            "cfg_scale": 7,
            "width": 512,
            "height": 512
        }
    }

    # GỬI JOB
    submit = requests.post(
        HORDE_SUBMIT,
        json=payload,
        headers=HEADERS,
        timeout=30
    )

    if submit.status_code != 202:
        raise HTTPException(502, "Stable Horde từ chối yêu cầu")

    job_id = submit.json().get("id")
    if not job_id:
        raise HTTPException(502, "Không nhận được job_id")

    # ĐỢI KẾT QUẢ
    for _ in range(60):  # ~120s
        time.sleep(2)

        status = requests.get(
            HORDE_STATUS.format(job_id),
            timeout=15
        ).json()

        if status.get("done"):
            gens = status.get("generations", [])
            if not gens:
                raise HTTPException(502, "AI không trả ảnh")

            img_url = gens[0].get("img")
            if not img_url:
                raise HTTPException(502, "Ảnh lỗi")

            img_data = requests.get(img_url, timeout=20).content

            with open(output_path, "wb") as f:
                f.write(img_data)
            return

    raise HTTPException(504, "AI xử lý quá lâu")

# =========================
# API TẠO PHOTO BOOK
# =========================
@app.post("/create-book")
async def create_book(
    prompt: str = Form(...),
    images: List[UploadFile] = Form(...)
):
    pages = []

    base_url = os.getenv("RENDER_EXTERNAL_URL", "http://127.0.0.1:8000")

    for i, img in enumerate(images):
        img_id = str(uuid.uuid4())
        input_path = f"uploads/{img_id}_{img.filename}"
        output_path = f"static/generated/{img_id}.png"

        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(img.file, buffer)

        # 🔥 GỌI STABLE DIFFUSION FREE
        call_stable_horde(prompt, output_path)

        pages.append({
            "page": i + 1,
            "image_url": f"{base_url}/{output_path}",
            "caption": f"AI tạo theo phong cách: {prompt}"
        })

    return {
        "title": "AI Photo Book",
        "total_pages": len(pages),
        "pages": pages
    }

# =========================
# RUN (LOCAL + RENDER)
# =========================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
