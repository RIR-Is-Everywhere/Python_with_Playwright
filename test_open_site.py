from playwright.sync_api import sync_playwright

def test_open_site_login():
    with sync_playwright() as p:
        # Launch browser (headless=False shows the browser)
        browser = p.chromium.launch(headless=False)
       
        # Open a new page
        page = browser.new_page()
       
        # Go to SauceDemo website
        page.goto("https://www.saucedemo.com/")
       
        # Print page title
        print("Page Title:", page.title())
       
        # --- LOGIN USING IDs ---
        page.locator("#user-name").fill("standard_user")
        page.wait_for_timeout(3000)
        page.locator("#password").fill("secret_sauce")
        page.wait_for_timeout(3000)    # Fill password
        page.click('#login-button')  
        page.wait_for_timeout(3000)  
        page.click('#add-to-cart-sauce-labs-backpack')    
        page.wait_for_timeout(3000)          # Click login button
       
        # Verify login by checking URL or page title
        print("After login, Page Title:", page.title())
     
       
        # Close browser
        browser.close()
