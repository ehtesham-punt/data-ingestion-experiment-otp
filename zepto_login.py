import asyncio
import logging

from playwright.async_api import async_playwright

# === Config ===
EXTENSION_PATH = "/Users/ehteshamtarique/Desktop/work-project/ShelfRadar-QConnect/chrome-extension"
USER_DATA_DIR = "/tmp/playwright_user_data"
EXTENSION_ID = "pnpljeedaeicppojfpfmgmdcikhpihjf"

OPTIONS_URL = f"chrome-extension://{EXTENSION_ID}/options.html"
POPUP_URL = f"chrome-extension://{EXTENSION_ID}/popup.html"
ZEPTO_BRAND_URL = "https://brands.zepto.co.in/login"

USER_KEY = "your-user-key"
API_ENV = "prod"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run():
    async with async_playwright() as p:
        logger.info("🚀 Launching Chromium with extension...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            args=[
                f"--disable-extensions-except={EXTENSION_PATH}",
                f"--load-extension={EXTENSION_PATH}",
            ],
        )

        # Step 1: Set extension settings
        logger.info("🧩 Opening options page...")
        options_page = await context.new_page()
        await options_page.goto(OPTIONS_URL)
        await options_page.wait_for_selector("#licenseKey")

        logger.info("✍️ Setting config...")
        await options_page.fill("#licenseKey", USER_KEY)
        await options_page.select_option("#apiBaseUrl", label="Production")
        await options_page.click("#save")
        await asyncio.sleep(1)
        await options_page.close()

        # Step 2: Open Zepto login page
        logger.info("🌐 Navigating to Zepto brand login...")
        zepto_tab = await context.new_page()
        await zepto_tab.goto(ZEPTO_BRAND_URL)
        logger.info("✅ Zepto page loaded.")

        logger.info("⚙️ Opening extension popup.html and clicking 'Start Sync'...")
        popup_page = await context.new_page()
        await popup_page.goto(POPUP_URL)
        await popup_page.wait_for_selector("#startSync")
        await popup_page.click("#startSync")
        logger.info("✅ 'Start Sync' button clicked.")

        logger.info("✅ Sync triggered. Browser is running.")
        print("🧩 Sync triggered via background message. Press CTRL+C to exit.")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(run())
