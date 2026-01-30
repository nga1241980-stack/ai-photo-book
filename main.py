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
os.makedirs("templates", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# =========================
# TRANG CHỦ
# =========================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# =========================
# STABLE HORDE (FREE - TỐI ƯU)
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
            "steps": 12,              # 🔥 GIẢM BƯỚC
            "cfg_scale": 6,
            "width": 384,             # 🔥 GIẢM SIZE
            "height": 384
        }
    }

    # GỬI JOB
    try:
        submit = requests.post(
            HORDE_SUBMIT,
            json=payload,
            headers=HEADERS,
            timeout=20
        )
    except:
        raise HTTPException(502, "Không kết nối được AI")

    if submit.status_code != 202:
        raise HTTPException(502, "AI từ chối yêu cầu")

    job_id = submit.json().get("id")
    if not job_id:
        raise HTTPException(502, "Không nhận được job_id")

    # ĐỢI KẾT QUẢ (tối đa ~4 phút, poll thưa)
    for _ in range(40):  # 40 x 6s = 240s
        time.sleep(6)

        try:
            status = requests.get(
                HORDE_STATUS.format(job_id),
                timeout=15
            ).json()
        except:
            continue

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

    raise HTTPException(504, "AI quá tải, thử lại sau")

# =========================
# API TẠO PHOTO BOOK (1 ẢNH / 1 LẦN)
# =========================
@app.post("/create-book")
async def create_book(
    prompt: str = Form(...),
    images: List[UploadFile] = Form(...)
):
    if len(images) > 1:
        raise HTTPException(400, "Chỉ upload 1 ảnh mỗi lần để tránh quá tải")

    pages = []
    base_url = os.getenv("RENDER_EXTERNAL_URL", "http://127.0.0.1:8000")

    img = images[0]
    img_id = str(uuid.uuid4())

    input_path = f"uploads/{img_id}_{img.filename}"
    output_path = f"static/generated/{img_id}.png"

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(img.file, buffer)

    # 🔥 GỌI AI
    call_stable_horde(prompt, output_path)

    pages.append({
        "page": 1,
        "image_url": f"{base_url}/{output_path}",
        "caption": f"AI tạo theo prompt: {prompt}"
    })

    return {
        "title": "AI Photo Book",
        "total_pages": 1,
        "pages": pages
    }

# =========================
# RUN
# =========================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
