import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import time

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("playwright_runner")


async def main():
    if len(sys.argv) < 2:
        result = {"status": "error", "message": "Missing input JSON"}
        print(json.dumps(result), flush=True)
        return

    try:
        config = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        result = {"status": "error", "message": "Invalid JSON"}
        print(json.dumps(result), flush=True)
        return

    # Extract config values
    username = config["username"]
    password = config["password"]
    api_key = config["api_key"]
    environment = config["environment"]
    login_url = config["login_url"]
    extension_path = config["extension_path"]
    options_url = config["options_url"]
    popup_url = config["popup_url"]

    # Extract file coordination paths
    otp_file = config["otp_file"]
    result_file = config["result_file"]

    # Write initial status to result file to indicate subprocess is running
    initial_status = {
        "status": "subprocess_created",
        "message": "Subprocess started, browser launching...",
    }
    with open(result_file, "w") as f:
        json.dump(initial_status, f)
    logger.info(f"📝 Initial status written to {result_file}")

    user_data_dir = tempfile.mkdtemp(prefix="pw_user_data_")

    try:
        logger.info("🧠 Starting browser...")

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
            ],
        )

        page = await browser.new_page()

        # Update status: browser ready
        browser_ready_status = {
            "status": "browser_ready",
            "message": "Browser launched, setting up extension...",
        }
        with open(result_file, "w") as f:
            json.dump(browser_ready_status, f)

        # Set extension options
        options_page = await browser.new_page()
        await asyncio.sleep(2)
        await options_page.goto(options_url)
        await options_page.wait_for_selector("#licenseKey")
        await options_page.fill("#licenseKey", api_key)
        await options_page.select_option("#apiBaseUrl", label=environment)
        await options_page.click("#save")
        await asyncio.sleep(1)
        await options_page.close()

        # Login to Zepto
        await page.goto(login_url)
        await page.get_by_role("textbox", name="Email").fill(username)
        await page.get_by_role("textbox", name="Password").fill(password)
        await page.get_by_role("button", name="Log In").click()

        # Update status: waiting for OTP
        otp_waiting_status = {
            "status": "waiting_for_otp",
            "message": "Login submitted, waiting for OTP...",
        }
        with open(result_file, "w") as f:
            json.dump(otp_waiting_status, f)

        logger.info("📩 Waiting for OTP file...")

        # Wait for OTP file
        otp = None
        max_otp_wait = 10 * 60  # 10 minutes timeout for OTP
        start_time = time.time()

        while not otp:
            if time.time() - start_time > max_otp_wait:
                raise Exception("Timeout waiting for OTP file")

            if os.path.exists(otp_file):
                try:
                    with open(otp_file) as f:
                        otp = f.read().strip()
                    logger.info(f"📨 Received OTP from file: {otp}")
                    break
                except Exception as e:
                    logger.warning(f"Failed to read OTP file: {e}")

            await asyncio.sleep(5)  # Check every 5 seconds

        # Submit OTP
        await page.get_by_role("textbox", name="OTP").fill(otp)
        await page.get_by_role("button", name="Confirm").click()

        # Update status: OTP submitted
        otp_submitted_status = {
            "status": "otp_submitted",
            "message": "OTP submitted, starting sync...",
        }
        with open(result_file, "w") as f:
            json.dump(otp_submitted_status, f)

        # Trigger extension sync
        popup_page = await browser.new_page()
        await popup_page.goto(popup_url)
        await popup_page.wait_for_selector("#startSync")
        await popup_page.click("#startSync")

        # Wait for sync completion
        await page.wait_for_timeout(90000)

        # Write final success result to file
        result = {"status": "success", "message": "Login and sync completed"}
        with open(result_file, "w") as f:
            json.dump(result, f)

        logger.info(f"✅ Final result written to {result_file}")

    except Exception as e:
        logger.exception("Login automation failed")
        # Write error result to file
        result = {"status": "error", "message": str(e)}
        with open(result_file, "w") as f:
            json.dump(result, f)

    finally:
        try:
            await browser.close()
        except Exception:
            pass
        await playwright.stop()
        shutil.rmtree(user_data_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
