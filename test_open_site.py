import os
import re
import zipfile
from pathlib import Path
from typing import TypedDict
import xml.etree.ElementTree as ET

import pytest
from playwright.sync_api import Page, expect, sync_playwright


# Base URL for the application under test.
BASE_URL = "https://www.saucedemo.com/"

# Selector for the error banner shown by Saucedemo on failed actions.
ERROR_SELECTOR = '[data-test="error"]'

# The Excel workbook that stores the 10 manual test cases.
WORKBOOK_PATH = Path(__file__).with_name("test_cases.xlsx")

# Namespace used to read Excel XML files inside the .xlsx archive.
XML_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class ExcelCase(TypedDict):
    # Unique ID from the spreadsheet, for example TC_01.
    case_id: str
    # Human-readable scenario name from the spreadsheet.
    scenario: str
    # Expected result text from the spreadsheet.
    expected_result: str


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    # Excel may store repeated text values in a shared string table instead of
    # putting plain text directly into each cell.
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    # Parse the shared string file and rebuild each string value in order.
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.findall(".//a:t", XML_NS))
        for item in root.findall("a:si", XML_NS)
    ]


def load_test_cases() -> list[ExcelCase]:
    # Stop early with a clear message if the workbook is missing.
    if not WORKBOOK_PATH.exists():
        raise FileNotFoundError(f"Workbook not found: {WORKBOOK_PATH}")

    # A .xlsx file is really a zip archive containing XML files.
    with zipfile.ZipFile(WORKBOOK_PATH) as archive:
        # Load the shared strings first so cell values can be resolved.
        strings = _shared_strings(archive)
        # Read the first worksheet where the test case rows live.
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    cases: list[ExcelCase] = []
    # Walk each row in the worksheet and translate it into Python data.
    for row in sheet.findall(".//a:sheetData/a:row", XML_NS):
        values: list[str] = []
        # Read each cell from the current row.
        for cell in row.findall("a:c", XML_NS):
            raw = cell.find("a:v", XML_NS)
            value = "" if raw is None else (raw.text or "")
            # Convert shared-string references into actual text values.
            if cell.attrib.get("t") == "s" and value:
                value = strings[int(value)]
            values.append(value.strip())

        # Keep only rows that represent real test cases like TC_01, TC_02, etc.
        if values and values[0].startswith("TC_"):
            # Pad short rows so we can safely access the expected columns.
            values += [""] * (4 - len(values))
            cases.append(
                {
                    # Column A: test case ID.
                    "case_id": values[0],
                    # Column B: scenario name.
                    "scenario": values[1].replace("\n", " ").strip(),
                    # Column D: expected result text.
                    "expected_result": values[3].replace("\n", " ").strip(),
                }
            )

    # Return the full list of Excel-driven test cases.
    return cases


# Load all cases once so pytest can parametrize the suite from this data.
TEST_CASES = load_test_cases()


@pytest.fixture
def page() -> Page:
    # Allow headed/headless behavior to be controlled from environment variables.
    headless = os.getenv("PW_HEADLESS", "true").lower() in {"1", "true", "yes"}
    slow_mo = int(os.getenv("PW_SLOW_MO_MS", "0"))

    # Start Playwright and create a fresh browser for each test so the tests do
    # not affect one another.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
        page = browser.new_page()

        # Always begin each test from the login page.
        page.goto(BASE_URL)

        # Give the test a ready-to-use page object.
        yield page

        # Close the browser after the test finishes.
        browser.close()


def login(page: Page, username: str, password: str) -> None:
    # Fill in the login form with the supplied credentials.
    page.fill("#user-name", username)
    page.fill("#password", password)

    # Submit the login form.
    page.click("#login-button")


def login_as_standard_user(page: Page) -> None:
    # Common helper for the happy-path login used by many test cases.
    login(page, "standard_user", "secret_sauce")

    # Confirm that login completed by waiting for the inventory page.
    expect(page).to_have_url(re.compile(r".*/inventory\.html$"))


def add_products(page: Page, count: int) -> None:
    # Grab all inventory buttons on the product page.
    buttons = page.locator(".inventory_item button")

    # Click the first `count` product buttons to add items to the cart.
    for index in range(count):
        buttons.nth(index).click()


def open_cart(page: Page) -> None:
    # Open the shopping cart from the top-right icon.
    page.locator(".shopping_cart_link").click()


def start_checkout(page: Page) -> None:
    # Checkout starts from the cart page.
    open_cart(page)

    # Click the checkout button to open the customer information form.
    page.locator('[data-test="checkout"]').click()


def fill_checkout(page: Page, first_name: str, last_name: str, postal_code: str) -> None:
    # Fill in the checkout information form.
    page.fill('[data-test="firstName"]', first_name)
    page.fill('[data-test="lastName"]', last_name)
    page.fill('[data-test="postalCode"]', postal_code)

    # Continue to the next step of checkout.
    page.locator('[data-test="continue"]').click()


def error_text(page: Page) -> str:
    # Return the visible error message in lowercase to make text checks simpler.
    return page.locator(ERROR_SELECTOR).inner_text().lower()


def run_case(page: Page, case_id: str) -> None:
    # Route each spreadsheet case ID to its matching automated behavior.
    if case_id == "TC_01":
        # Valid login should land on the inventory page.
        login_as_standard_user(page)
        expect(page.locator(".title")).to_have_text("Products")
    elif case_id == "TC_02":
        # Invalid credentials should show a login error.
        login(page, "invalid_user", "wrong_pass")
        expect(page.locator(ERROR_SELECTOR)).to_be_visible()
        assert "do not match" in error_text(page)
    elif case_id == "TC_03":
        # Empty login fields should trigger the required-username message.
        login(page, "", "")
        expect(page.locator(ERROR_SELECTOR)).to_be_visible()
        assert "username is required" in error_text(page)
    elif case_id == "TC_04":
        # After login, the inventory page should show products with visible details.
        login_as_standard_user(page)
        expect(page.locator(".inventory_item")).to_have_count(6)
        expect(page.locator(".inventory_item_name").first).to_be_visible()
        expect(page.locator(".inventory_item_price").first).to_be_visible()
        expect(page.locator(".inventory_item button").first).to_have_text("Add to cart")
    elif case_id == "TC_05":
        # Adding one product should update the cart badge and button text.
        login_as_standard_user(page)
        add_products(page, 1)
        expect(page.locator(".shopping_cart_badge")).to_have_text("1")
        expect(page.locator(".inventory_item button").first).to_have_text("Remove")
    elif case_id == "TC_06":
        # Adding three products should show a cart count of three.
        login_as_standard_user(page)
        add_products(page, 3)
        expect(page.locator(".shopping_cart_badge")).to_have_text("3")
    elif case_id == "TC_07":
        # Removing a previously added product should clear the cart badge.
        login_as_standard_user(page)
        add_products(page, 1)
        page.locator(".inventory_item button").first.click()
        expect(page.locator(".shopping_cart_badge")).to_have_count(0)
        expect(page.locator(".inventory_item button").first).to_have_text("Add to cart")
    elif case_id == "TC_08":
        # Opening the cart should show the selected product on the cart page.
        login_as_standard_user(page)
        add_products(page, 1)
        open_cart(page)
        expect(page).to_have_url(re.compile(r".*/cart\.html$"))
        expect(page.locator(".cart_item")).to_have_count(1)
    elif case_id == "TC_09":
        # Missing checkout information should show the first-name-required error.
        login_as_standard_user(page)
        add_products(page, 1)
        start_checkout(page)
        fill_checkout(page, "", "", "")
        expect(page.locator(ERROR_SELECTOR)).to_be_visible()
        assert "first name is required" in error_text(page)
    elif case_id == "TC_10":
        # A full checkout should reach the completion page and show confirmation.
        login_as_standard_user(page)
        add_products(page, 1)
        start_checkout(page)
        fill_checkout(page, "John", "Doe", "12345")
        page.locator('[data-test="finish"]').click()
        expect(page).to_have_url(re.compile(r".*/checkout-complete\.html$"))
        expect(page.locator(".complete-header")).to_have_text("Thank you for your order!")
    else:
        # Fail loudly if the spreadsheet contains a case ID we do not support yet.
        raise AssertionError(f"Unsupported test case ID: {case_id}")


@pytest.mark.parametrize("case", TEST_CASES, ids=[case["case_id"] for case in TEST_CASES])
def test_saucedemo_cases_from_excel(page: Page, case: ExcelCase) -> None:
    # Pytest turns this one function into 10 separate tests using the Excel data.
    run_case(page, case["case_id"])
