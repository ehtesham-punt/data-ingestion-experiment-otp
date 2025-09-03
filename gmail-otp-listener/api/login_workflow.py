import asyncio
import logging
import tempfile
from typing import Literal

from playwright.async_api import async_playwright
from pydantic import BaseModel
from restate import Workflow

# === INPUT / OUTPUT SCHEMAS ===


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


# === WORKFLOW ===

login_wf = Workflow("login_workflow")

EXTENSION_PATH = "/Users/ehteshamtarique/Desktop/work-project/ShelfRadar-QConnect/chrome-extension"
EXTENSION_ID = "pnpljeedaeicppojfpfmgmdcikhpihjf"
OPTIONS_URL = f"chrome-extension://{EXTENSION_ID}/options.html"
POPUP_URL = f"chrome-extension://{EXTENSION_ID}/popup.html"
ZEPTO_BRAND_URL = "https://brands.zepto.co.in/login"


@login_wf.main()
async def login_workflow(ctx, input_config: LoginInput) -> LoginOutput:
    logger = logging.getLogger(__name__)
    logger.info(
        f"Starting login for {input_config.platformSync} with user: {input_config.username}"
    )

    playwright = await async_playwright().start()
    user_data_dir = tempfile.mkdtemp(prefix="playwright_user_data_")

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=False,
        args=[
            f"--disable-extensions-except={EXTENSION_PATH}",
            f"--load-extension={EXTENSION_PATH}",
        ],
    )

    page = await context.new_page()

    try:
        if input_config.platformSync == "zepto":
            # Step 1: Set extension settings
            logger.info("🧩 Opening options page...")
            options_page = await context.new_page()
            await options_page.goto(OPTIONS_URL)
            await options_page.wait_for_selector("#licenseKey")

            logger.info("✍️ Setting config...")
            await options_page.fill("#licenseKey", input_config.api_key)
            await options_page.select_option("#apiBaseUrl", label=input_config.environment)
            await options_page.click("#save")
            await asyncio.sleep(1)
            await options_page.close()

            # Step 2: Perform Zepto login
            logger.info("🌐 Navigating to Zepto brand login...")
            await page.goto(ZEPTO_BRAND_URL)
            await page.get_by_role("textbox", name="Email").fill(input_config.username)
            await page.get_by_role("textbox", name="Password").fill(input_config.password)
            await page.get_by_role("button", name="Log In").click()

            # Step 3: Wait for OTP input via Restate
            logger.info("🕐 Waiting for OTP from promise...")
            otp_value = await asyncio.wait_for(ctx.promise("otp_wait"), timeout=500)
            logger.info(f"✅ Received OTP: {otp_value}")

            # Step 4: Fill OTP and confirm
            await page.get_by_role("textbox", name="OTP").fill(otp_value)
            await page.get_by_role("button", name="Confirm").click()
            logger.info("🔐 OTP submitted and login confirmed.")

            # Step 5: Trigger sync from extension popup
            logger.info("⚙️ Opening extension popup and triggering sync...")
            popup_page = await context.new_page()
            await popup_page.goto(POPUP_URL)
            await popup_page.wait_for_selector("#startSync")
            await popup_page.click("#startSync")
            logger.info("✅ 'Start Sync' triggered.")

            # Optional wait to ensure sync is complete
            await page.wait_for_timeout(90000)

            # Step 6: Suspend workflow and wait for 'complete_workflow' signal
            logger.info(
                "⏸️ Suspending workflow. Waiting for 'complete_workflow' promise to be resolved..."
            )
            complete_promise = ctx.promise("complete_wait")
            await complete_promise  # Suspend here until handler resolves
            logger.info("✅ Received workflow completion signal.")

            return LoginOutput(status="success", otp=otp_value)

        else:
            raise Exception(f"Platform {input_config.platformSync} is not yet supported.")

    except asyncio.TimeoutError:
        logger.exception("OTP was not received in time.")
        await context.close()
        await playwright.stop()
        raise
    except Exception:
        logger.exception("Login workflow failed.")
        raise


@login_wf.handler(name="receive_otp")
async def receive_otp(ctx, otp_data: OTPInput):
    logger = logging.getLogger(__name__)
    logger.info(f"Received OTP: {otp_data.otp}")
    otp_promise = ctx.promise("otp_wait")
    await otp_promise.resolve(otp_data.otp)
    return {"status": "otp_received"}


@login_wf.handler(name="complete_workflow")
async def complete_workflow(ctx):
    logger = logging.getLogger(__name__)
    logger.info("✅ Workflow completed successfully.")
    complete_promise = ctx.promise("complete_wait")
    await complete_promise.resolve("done")  # Any value is fine
    return {"status": "workflow_completed"}
