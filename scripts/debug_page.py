from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        headless=True
    )
    page = browser.new_page()
    page.goto("http://127.0.0.1:8000/signup")
    page.wait_for_timeout(2000)
    print("URL:", page.url)
    print("Title:", page.title())
    print("HTML excerpt:\n", page.content()[:1000])
    browser.close()
