import asyncio
import json
import logging
import os
from typing import Literal

from pydantic import BaseModel
from restate import Workflow

# === Constants ===
EXTENSION_PATH = "/Users/ehteshamtarique/Desktop/work-project/ShelfRadar-QConnect/chrome-extension"
EXTENSION_ID = "pnpljeedaeicppojfpfmgmdcikhpihjf"
OPTIONS_URL = f"chrome-extension://{EXTENSION_ID}/options.html"
POPUP_URL = f"chrome-extension://{EXTENSION_ID}/popup.html"
ZEPTO_BRAND_URL = "https://brands.zepto.co.in/login"

login_wf = Workflow("login_workflow")


# === Schemas ===
class LoginInput(BaseModel):
    platformSync: Literal["zepto", "swiggy", "blinkit"]
    username: str
    password: str
    api_key: str
    environment: Literal["Production", "Staging", "Local"]


class LoginOutput(BaseModel):
    status: str
    otp: str


class OTPInput(BaseModel):
    otp: str


# === Main Workflow ===
@login_wf.main()
async def login_workflow(ctx, input_config: LoginInput) -> LoginOutput:
    logger = logging.getLogger(__name__)
    logger.info(f"🚀 Starting login for {input_config.platformSync}")

    if input_config.platformSync != "zepto":
        raise Exception(f"Platform {input_config.platformSync} is not supported.")

    # Build input dict for subprocess
    input_dict = input_config.dict()

    # Create unique coordination files for this workflow instance
    workflow_id = ctx.key() or "default"
    otp_file = f"/tmp/otp_{workflow_id}.txt"
    result_file = f"/tmp/result_{workflow_id}.txt"

    # Delete existing files if they exist (for clean replay state)
    for file_path in [otp_file, result_file]:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"🗑️ Deleted existing file: {file_path}")

    input_dict.update({
        "extension_path": EXTENSION_PATH,
        "options_url": OPTIONS_URL,
        "popup_url": POPUP_URL,
        "login_url": ZEPTO_BRAND_URL,
        "otp_file": otp_file,
        "result_file": result_file,
    })

    # === Launch subprocess safely (only once) ===
    async def create_subprocess():
        # Check if subprocess is already running by checking for result file
        if os.path.exists(result_file):
            logger.info("📋 Checking existing subprocess status...")
            with open(result_file) as f:
                existing_status = json.loads(f.read())

            # If subprocess is still running (not final status), don't create new one
            if existing_status.get("status") in [
                "subprocess_created",
                "browser_ready",
                "waiting_for_otp",
                "otp_submitted",
            ]:
                logger.info(f"🔄 Subprocess already running: {existing_status.get('message')}")
                return {"subprocess_already_running": True, "current_status": existing_status}

            # If subprocess completed, return the final result
            if existing_status.get("status") in ["success", "error"]:
                logger.info("📋 Subprocess already completed, reading result...")
                return existing_status

        command = ["python3", "api/playwright_login_runner.py", json.dumps(input_dict)]
        logger.info("🧠 Launching new subprocess...")

        # Start subprocess in fire-and-forget mode
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait a moment for the initial status file to be created
        await asyncio.sleep(2)

        logger.info(f"🚀 Subprocess started with PID: {proc.pid}")
        return {"subprocess_started": True, "pid": proc.pid}

    subprocess_info = await ctx.run("create_subprocess", create_subprocess)

    # If subprocess already completed, return early
    if "status" in subprocess_info:
        return LoginOutput(status="success", otp="cached")

    # === Wait for OTP (replay-safe) ===
    otp_value = await asyncio.wait_for(ctx.promise("otp_wait"), timeout=300)  # 5 minutes
    logger.info(f"🔐 Received OTP from handler: {otp_value}")

    # === Write OTP to file for subprocess to read ===
    async def write_otp_and_wait():
        # Write OTP to coordination file
        with open(otp_file, "w") as f:
            f.write(otp_value)
        logger.info(f"📝 OTP written to {otp_file}")

        # Wait for result file with polling
        max_wait_time = 5 * 60 * 60  # 5 hours in seconds
        start_time = asyncio.get_event_loop().time()

        while True:
            current_time = asyncio.get_event_loop().time()
            if current_time - start_time > max_wait_time:
                logger.error("⏰ Subprocess timeout after 5 hours")
                # Clean up coordination files
                for file_path in [otp_file, result_file]:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                raise Exception("Subprocess execution timed out after 5 hours")

            # Check if result file exists
            if os.path.exists(result_file):
                try:
                    with open(result_file) as f:
                        result = json.loads(f.read())

                    # Only return if it's a final status
                    if result.get("status") in ["success", "error"]:
                        # Clean up coordination files
                        for file_path in [otp_file, result_file]:
                            if os.path.exists(file_path):
                                os.remove(file_path)

                        if result.get("status") != "success":
                            raise Exception(result.get("message", "Login failed in subprocess"))
                        return result
                except Exception as e:
                    logger.exception("🧨 Failed to parse subprocess result")
                    raise Exception(f"Failed to parse subprocess result: {e}")

            # Wait before checking again
            await asyncio.sleep(10 * 60)  # Check every 10 minutes

    result = await ctx.run("write_otp_and_wait", write_otp_and_wait)

    return LoginOutput(status="success", otp=otp_value)


# === OTP Handler ===
@login_wf.handler(name="receive_otp")
async def receive_otp(ctx, otp_data: OTPInput):
    logger = logging.getLogger(__name__)
    logger.info(f"📨 Received OTP: {otp_data.otp}")
    await ctx.promise("otp_wait").resolve(otp_data.otp)
    return {"status": "otp_received"}


# === Completion Handler ===
@login_wf.handler(name="complete_workflow")
async def complete_workflow(ctx):
    logger = logging.getLogger(__name__)
    logger.info("✅ Workflow marked as complete.")
    await ctx.promise("complete_wait").resolve("done")
    return {"status": "workflow_completed"}
