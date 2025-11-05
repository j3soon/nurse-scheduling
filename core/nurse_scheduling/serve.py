"""
FastAPI backend for Nurse Scheduling System.
Receives a YAML file and returns an optimized XLSX schedule.
"""
import logging
from datetime import datetime
from io import BytesIO
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from typing import Optional
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from . import scheduler, exporter

# Configure logging to verbose level 1 (verbose levels defined in CLI)
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

title = "Nurse Scheduling API"
version = "alpha"

app = FastAPI(
    title=title,
    version=version
)

origins = [
    # For Next.js local development
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://kaichen0712.github.io",
    # TODO: Add hosted URL and note on self-hosting
]

expose_headers = [
    "Content-Disposition",
    "X-Schedule-Score",
    "X-Schedule-Status",
]

# Configure CORS to only allow trusted frontend origins in order to
# prevent Cross-Site Request Forgery (CSRF) attacks.
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
    expose_headers=expose_headers,
)


@app.get("/")
async def root():
    return {
        "message": title,
        "version": version
    }

# TODO: Check args
@app.post("/optimize-and-export-xlsx")
async def optimize_and_export_xlsx(
    file: Optional[UploadFile] = File(None, description="YAML file with scheduling data"),
    yaml_content: Optional[str] = Form(None, description="YAML content as a string"),
    prettify: Optional[bool] = Form(None, description="Enable prettier output formatting"),
    timeout: Optional[int] = Form(None, description="Max execution time in seconds")
):
    """
    Optimize a nurse schedule from a YAML file or YAML string, and return an XLSX file.

    Either `file` or `yaml_content` must be provided (not both).
    """
    # Validate that exactly one input method is provided
    if file is None and yaml_content is None:
        raise HTTPException(
            status_code=400,
            detail="Either 'file' or 'yaml_content' must be provided"
        )
    
    if file is not None and yaml_content is not None:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'file' or 'yaml_content', not both"
        )
    
    # Read content from file or use provided yaml_content
    if file is not None:
        # Validate that the uploaded file is a YAML file (sanity check, not for security)
        if not file.filename.endswith(('.yaml', '.yml')):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Please upload a YAML file (.yaml or .yml)"
            )
        content = await file.read()
        input_name = file.filename
    else:
        # Use yaml_content string directly
        content = yaml_content.encode('utf-8')
        input_name = f"nurse-scheduling-{datetime.now().strftime('%Y%m%d%H%M%S')}.yaml"
    
    logging.info(f"Processing schedule optimization...")
    logging.info(f"Input: {input_name}")
    logging.info(f"Prettify: {prettify}, Timeout: {timeout}")

    try:
        # Run the scheduler with file content directly
        # TODO(security): May need to add security checks to prevent injection attacks or misuse
        df, solution, score, status, cell_export_info = scheduler.schedule(
            file_content=content,
            prettify=prettify,
            timeout=timeout
        )
        
    except Exception as e:
        # TODO(security): Returning the error message to the client may be a security risk
        logging.error(f"Error during optimization: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error during optimization: {str(e)}"
        )
        
    if df is None:
        raise HTTPException(
            status_code=400,
            detail="No solution found. The constraints may be too restrictive."
        )
    
    # Export to Excel in memory
    output_buffer = BytesIO()
    exporter.export_to_excel(df, output_buffer, cell_export_info)
    
    logging.info(f"Optimization complete. Score: {score}, Status: {status}")
    
    # Generate output filename
    base_filename = input_name.rsplit('.', 1)[0]
    output_filename = f"{base_filename}.xlsx"
    
    # Return the file from memory
    return StreamingResponse(
        output_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={output_filename}",
            "X-Schedule-Score": str(score),
            "X-Schedule-Status": str(status)
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
