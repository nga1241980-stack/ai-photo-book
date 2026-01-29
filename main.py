from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

# =========================
# STABLE HORDE API
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
        "models": ["stable_diffusion"],  # model dễ có worker
        "params": {
            "sampler_name": "k_euler",
            "steps": 20,
            "cfg_scale": 7,
            "width": 512,
            "height": 512
        }
    }

    # ===== GỬI JOB =====
    try:
        submit = requests.post(
            HORDE_SUBMIT,
            json=payload,
            headers=HEADERS,
            timeout=20
        )
    except Exception:
        raise HTTPException(502, "Không kết nối được Stable Horde")

    if submit.status_code != 202:
        raise HTTPException(502, "Stable Horde từ chối yêu cầu")

    job_id = submit.json().get("id")
    if not job_id:
        raise HTTPException(502, "Không nhận được job_id")

    # ===== POLL KẾT QUẢ =====
    for _ in range(60):  # ~120s
        time.sleep(2)

        try:
            status = requests.get(
                HORDE_STATUS.format(job_id),
                timeout=10
            ).json()
        except Exception:
            continue

        if status.get("done"):
            gens = status.get("generations", [])
            if not gens:
                raise HTTPException(502, "AI không trả ảnh")

            img_url = gens[0].get("img")
            if not img_url:
                raise HTTPException(502, "Ảnh không hợp lệ")

            try:
                img_data = requests.get(img_url, timeout=20).content
            except Exception:
                raise HTTPException(502, "Không tải được ảnh")

            with open(output_path, "wb") as f:
                f.write(img_data)
            return

    raise HTTPException(504, "AI xử lý quá lâu (timeout)")


# =========================
# API TẠO SÁCH
# =========================
@app.post("/create-book")
async def create_book(
    prompt: str = Form(...),
    images: List[UploadFile] = Form(...)
):
    pages = []

    for i, img in enumerate(images):
        img_id = str(uuid.uuid4())
        input_path = f"uploads/{img_id}_{img.filename}"
        output_path = f"static/generated/{img_id}.png"

        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(img.file, buffer)

        call_stable_horde(prompt, output_path)

        pages.append({
            "page": i + 1,
            "image_url": f"http://127.0.0.1:8000/{output_path}",
            "caption": f"AI tạo theo phong cách: {prompt}"
        })

    return {
        "title": "AI Photo Book",
        "total_pages": len(pages),
        "pages": pages
    }


# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
