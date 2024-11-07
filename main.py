from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import io
import subprocess
import os
import shutil
from pathlib import Path
import tempfile
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/hello")
def read_root():
    return {"message": "Test with FastAPI"}

async def convert_dwg_to_dxf_file(input_file: str, output_file: str) -> bool:
    try:
        logger.info(f"Converting file: {input_file} to {output_file}")

        # 명령어 수정
        result = subprocess.run([
            'dwg2dxf',
            '-v',
            '--as',
            'r2000',
            '-b',
            input_file
        ], capture_output=True, text=True)

        logger.info(f"Command output: {result.stdout}")
        logger.error(f"Command errors: {result.stderr}")

        # DXF 파일이 생성되었는지 확인
        output_dxf = input_file.replace('.dwg', '.dxf')
        if os.path.exists(output_dxf):
            # 생성된 파일을 원하는 위치로 이동
            shutil.move(output_dxf, output_file)

        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            logger.info(f"Successfully created DXF file: {output_file}")
            return True

        logger.error("Failed to create output file or file is empty")
        return False

    except Exception as e:
        logger.exception(f"Error during conversion: {str(e)}")
        return False

@app.post("/api/dwg2dxf")
async def convert_dwg_to_dxf(file: UploadFile):
    if not file.filename.lower().endswith('.dwg'):
        raise HTTPException(status_code=400, detail="DWG 파일만 업로드 가능합니다.")

    temp_dir = tempfile.mkdtemp(prefix='dwg2dxf_')
    temp_input = os.path.join(temp_dir, "input.dwg")
    temp_output = os.path.join(temp_dir, "output.dxf")

    try:
        content = await file.read()
        with open(temp_input, "wb") as buffer:
            buffer.write(content)

        logger.info(f"Saved input file: {temp_input} (size: {len(content)} bytes)")

        success = await convert_dwg_to_dxf_file(temp_input, temp_output)

        if not success:
            raise HTTPException(status_code=500, detail="파일 변환에 실패했습니다.")

        if not os.path.exists(temp_output):
            raise HTTPException(status_code=500, detail="변환된 파일이 생성되지 않았습니다.")

        file_size = os.path.getsize(temp_output)
        logger.info(f"Created output file: {temp_output} (size: {file_size} bytes)")

        # 파일을 메모리에 읽어들임
        with open(temp_output, 'rb') as f:
            file_content = f.read()

        # 임시 파일들 정리
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logger.error(f"Failed to clean up temp files: {str(e)}")

        # 메모리에서 스트리밍으로 파일 반환
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type='application/dxf',
            headers={
                'Content-Disposition': f'attachment; filename="{file.filename.replace(".dwg", ".dxf")}"'
            }
        )

    except Exception as e:
        # 에러 발생시 임시 파일 정리
        try:
            shutil.rmtree(temp_dir)
        except Exception as cleanup_error:
            logger.error(f"Failed to clean up temp files: {str(cleanup_error)}")

        logger.exception(f"Error during processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))